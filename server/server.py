import csv
from datetime import datetime
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import ssl
import json
import numpy as np
import os
import biosppy.signals.ppg as ppg
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app, cors_allowed_origins='*')

# MQTT 설정
MQTT_BROKER_URL = 'msg01.cloudiot.ntruss.com'
MQTT_BROKER_PORT = 8883
MQTT_TOPIC = 'alert'
CA_CERTS = './server/rootCaCert.pem'
CERTFILE = './server/cert.pem'
KEYFILE = './server/private.pem'

# MQTT 클라이언트 설정
mqtt_client = mqtt.Client()

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

# MQTT 연결이 수립되었을 때 실행되는 콜백 함수
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    if rc == 0:
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"Failed to connect, return code {rc}")

# MQTT 메시지가 도착했을 때 실행되는 콜백 함수
def on_message(client, userdata, msg):
    global ir_data_list, red_data_list

    data = msg.payload.decode()
    print(f"Received message: {data}")

    try:
        payload = json.loads(data)
        ir_value = int(payload['ir'])
        red_value = int(payload['red'])
        ir_data_list.append(ir_value)
        red_data_list.append(red_value)
        additional_data_list.extend([(ir_value, red_value)])

        # 일정 개수 이상 데이터가 모이면 처리
        if len(ir_data_list) > 80:
            process_ppg_data()

    except Exception as e:
        print(f"Error processing MQTT message: {e}")

# PPG 데이터를 처리하는 함수
def process_ppg_data():
    global ir_data_list, red_data_list, csv_file_label

    try:
        print(f"Processing {len(ir_data_list)} IR data points")

        # 리스트를 numpy 배열로 변환
        signal = np.array(ir_data_list, dtype=np.float64)

        # 신호 처리
        out = ppg.ppg(signal=signal, sampling_rate=50., show=False)

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

        # 추가 데이터 리스트에 데이터 추가
        # additional_data_list.extend(zip(ir_data_list, red_data_list))

        # 처리가 끝난 후 데이터 리스트 초기화
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

# 메인 함수
if __name__ == '__main__':
    # MQTT 클라이언트 설정
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    # TLS 설정
    mqtt_client.tls_set(ca_certs=CA_CERTS, certfile=CERTFILE, keyfile=KEYFILE, tls_version=ssl.PROTOCOL_TLSv1_2)
    mqtt_client.tls_insecure_set(False)

    # MQTT 브로커에 연결
    mqtt_client.connect(MQTT_BROKER_URL, MQTT_BROKER_PORT, 60)

    # MQTT 메시지 수신을 위한 루프 시작
    mqtt_client.loop_start()

    # Flask 애플리케이션 실행 (SocketIO 포함)
    socketio.run(app, host='0.0.0.0', port=5000)
