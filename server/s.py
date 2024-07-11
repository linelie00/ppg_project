import csv
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import os
import biosppy.signals.ppg as ppg
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app, cors_allowed_origins='*')
CORS(app)

# 데이터를 저장할 리스트
ir_data_list = []
red_data_list = []
additional_data_list = []
csv_file_label = 'default'

# CSV 파일 관리
csv_file = None
csv_writer = None

# CSV 파일을 열고 데이터를 저장하는 함수
def open_csv_file(label):
    global csv_file, csv_writer

    # 현재 시간을 기반으로 파일명 생성
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'csv/ppg_data_{label}_{timestamp}.csv'

    # csv 디렉터리가 없으면 생성
    if not os.path.exists('csv'):
        os.makedirs('csv')

    # 파일 열기
    csv_file = open(filename, mode='a', newline='')
    csv_writer = csv.writer(csv_file)

    # 파일에 헤더 쓰기 (새로운 파일일 경우에만)
    if os.path.getsize(filename) == 0:
        csv_writer.writerow(['IR Value', 'Red Value'])

    print(f"Opened CSV file: {filename}")

# CSV 파일을 닫는 함수
def close_csv_file():
    global csv_file
    if csv_file:
        csv_file.close()
        csv_file = None
        print("Closed CSV file")

# PPG 데이터를 처리하는 함수
def process_ppg_data():
    global ir_data_list, red_data_list

    try:
        print(f"Processing {len(ir_data_list)} IR data points")

        # 리스트를 numpy 배열로 변환
        signal = np.array(ir_data_list, dtype=np.float64)

        # 신호 처리
        out = ppg.ppg(signal=signal, sampling_rate=50., show=False)

        # 피크가 2개 이상인 경우에만 심박수 계산
        if len(out['peaks']) >= 2:
            # 피크 간 시간 간격을 계산하여 심박수 추정
            diff = (out['peaks'][1] - out['peaks'][0]) / 50.0  # 시간 간격 계산
            heart_rate = 60.0 / diff  # 심박수 계산
        else:
            heart_rate = None

        # 클라이언트에게 데이터 전송
        response = {
            'ts': out['ts'].tolist(),
            'filtered': out['filtered'].tolist(),
            'peaks': out['peaks'].tolist(),
            'heart_rate': heart_rate
        }
        socketio.emit('ppg_data', response)

        # 추가 데이터 리스트 초기화
        ir_data_list.clear()
        red_data_list.clear()

    except Exception as e:
        print(f"Error processing PPG data: {e}")

# 클라이언트에서 데이터 초기화 요청이 왔을 때 실행되는 콜백 함수
@socketio.on('reset_data')
def handle_reset_data(data):
    global csv_file_label

    print(f"Resetting PPG data with new label: {data['label']}")

    # CSV 파일 닫기
    close_csv_file()

    # 추가 데이터를 CSV 파일에 추가
    if additional_data_list:
        try:
            open_csv_file(csv_file_label)
            csv_writer.writerows(additional_data_list)
            print(f"Added {len(additional_data_list)} additional data points to CSV")
        except Exception as e:
            print(f"Error writing additional data to CSV: {e}")
        finally:
            close_csv_file()

    # 추가 데이터 리스트 초기화
    additional_data_list.clear()
    ir_data_list.clear()
    red_data_list.clear()

    # 새로운 레이블 설정
    csv_file_label = data['label']

# POST 요청을 받는 엔드포인트
@app.route('/esp32Test', methods=['POST'])
def receive_data():
    try:
        # JSON 데이터 수신 시도
        data = request.get_json(silent=True)
        print(f"Received data: {data}")
        
        if data and 'ir' in data and 'red' in data and isinstance(data['ir'], list) and isinstance(data['red'], list):
            ir_values = data['ir']
            red_values = data['red']
            
            for ir_value, red_value in zip(ir_values, red_values):
                ir_data_list.append(int(ir_value))
                red_data_list.append(int(red_value))
                additional_data_list.append((int(ir_value), int(red_value)))
        
        # 데이터가 일정 개수 이상 모이면 처리
        if len(ir_data_list) > 80:
            process_ppg_data()

        return jsonify({'message': 'Data received successfully'})

    except Exception as e:
        print(f"Error receiving data via HTTP POST: {e}")
        return jsonify({'error': str(e)}), 500

# 메인 함수
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
