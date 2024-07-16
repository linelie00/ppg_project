import csv
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import os
import biosppy.signals.ppg as ppg
from flask_socketio import SocketIO, emit
import math
from scipy.signal import butter, filtfilt

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
    timestamp = datetime.now().strftime('%y%m%d-%H-%M')
    filename = f'csv/{label}_{timestamp}.csv'

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

# High-pass filter function to remove the DC component
def highpass_filter(data, cutoff_frequency, sampling_frequency):
    nyquist_frequency = 0.5 * sampling_frequency
    normal_cutoff = cutoff_frequency / nyquist_frequency
    b, a = butter(1, normal_cutoff, btype='high', analog=False)
    y = filtfilt(b, a, data)
    return y

# Band-pass filter function to remove noise
def bandpass_filter(signal, lowcut, highcut, fs, order=5):
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist
    b, a = butter(order, [low, high], btype='band')
    y = filtfilt(b, a, signal)
    return y

# RMS calculation function
def calculate_rms(data):
    square_sum = sum([i**2 for i in data])
    mean = square_sum / len(data)
    rms = math.sqrt(mean)
    return rms

# SpO2 calculation function
def calculate_spo2(ir_data, red_data):
    sampling_frequency = 50  # Assume a sampling frequency of 50 Hz
    cutoff_frequency = 0.5   # Adjust the cutoff frequency as needed
    
    ac_component_ir = highpass_filter(ir_data, cutoff_frequency, sampling_frequency)
    dc_component_ir = ir_data - ac_component_ir
    ac_component_red = highpass_filter(red_data, cutoff_frequency, sampling_frequency)
    dc_component_red = red_data - ac_component_red

    red_rms_ac = calculate_rms(bandpass_filter(ac_component_red, 0.5, 5, sampling_frequency))
    ir_rms_ac = calculate_rms(bandpass_filter(ac_component_ir, 0.5, 5, sampling_frequency))
    ratio = (red_rms_ac / np.mean(dc_component_red)) / (ir_rms_ac / np.mean(dc_component_ir))

    spo2 = 110 - 25 * ratio  # Adjust the coefficient as per the calibration
    return spo2

# PPG 데이터를 처리하는 함수
def process_ppg_data():
    global ir_data_list, red_data_list

    try:
        print(f"Processing {len(ir_data_list)} IR data points")

        # 심박수 계산
        signal = np.array(ir_data_list, dtype=np.float64)
        out = ppg.ppg(signal=signal, sampling_rate=50., show=False)

        if len(out['peaks']) >= 2:
            diff = (out['peaks'][1] - out['peaks'][0]) / 50.0
            heart_rate = int(60.0 / diff)
        else:
            heart_rate = None

        # 산소포화도 계산
        spo2 = int(calculate_spo2(np.array(ir_data_list), np.array(red_data_list)))

        response = {
            'ts': out['ts'].tolist(),
            'filtered': out['filtered'].tolist(),
            'peaks': out['peaks'].tolist(),
            'heart_rate': heart_rate,
            'spo2': spo2
        }
        socketio.emit('ppg_data', response)

        ir_data_list.clear()
        red_data_list.clear()

    except Exception as e:
        print(f"Error processing PPG data: {e}")

@socketio.on('reset_data')
def handle_reset_data(data):
    socketio.emit('reset_server', data)

@socketio.on('save_data')
def handle_save_data(data):
    global csv_file_label

    age = data.get('age', 'unknown')
    species = data.get('species', 'unknown')
    weight = data.get('weight', 'unknown')
    disease = data.get('disease', 'unknown')

    csv_file_label = f"{age}_{species}_{weight}_{disease}"

    print(f"Resetting PPG data with new label: {csv_file_label}")

    close_csv_file()

    if additional_data_list:
        try:
            open_csv_file(csv_file_label)
            csv_writer.writerows(additional_data_list)
            print(f"Added {len(additional_data_list)} additional data points to CSV")
        except Exception as e:
            print(f"Error writing additional data to CSV: {e}")
        finally:
            close_csv_file()

    additional_data_list.clear()
    ir_data_list.clear()
    red_data_list.clear()

@app.route('/esp32Test', methods=['POST'])
def receive_data():
    try:
        data = request.get_json(silent=True)
        print(f"Received data: {data}")
        
        if data and 'ir' in data and 'red' in data and isinstance(data['ir'], list) and isinstance(data['red'], list):
            ir_values = data['ir']
            red_values = data['red']

            for ir_value, red_value in zip(ir_values, red_values):
                ir_data_list.append(int(ir_value))
                red_data_list.append(int(red_value))
                additional_data_list.append((int(ir_value), int(red_value)))
        
        if len(ir_data_list) > 80:
            process_ppg_data()

        # Check if values are within the specified range
        if any(10 <= val <= 10000 for val in ir_values) or any(10 <= val <= 10000 for val in red_values):
            socketio.emit('request_retake', {'message': 'Please retake the measurement, data values are out of range.'})
            return jsonify({'message': 'Please retake the measurement, data values are out of range.'}), 400

        return jsonify({'message': 'Data received successfully'})

    except Exception as e:
        print(f"Error receiving data via HTTP POST: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
