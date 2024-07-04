from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
import ssl
import json
import biosppy.signals.ppg as ppg
import numpy as np

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
ppg_data_list = []

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    if rc == 0:
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    data = msg.payload.decode()
    print(f"Received message: {data}")

    # 데이터를 리스트에 추가
    ppg_data_list.append(int(json.loads(data)['value']))  # 'value'를 int로 변환하여 추가

    # 데이터가 일정 개수 이상일 때 처리 함수 호출
    if len(ppg_data_list) >= 70:
        process_ppg_data()

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# TLS 설정
mqtt_client.tls_set(ca_certs=CA_CERTS, certfile=CERTFILE, keyfile=KEYFILE, tls_version=ssl.PROTOCOL_TLSv1_2)
mqtt_client.tls_insecure_set(False)

mqtt_client.connect(MQTT_BROKER_URL, MQTT_BROKER_PORT, 60)

def process_ppg_data():
    global ppg_data_list
    try:
        print(f"Processing {len(ppg_data_list)} PPG data points")

        # 리스트를 numpy 배열로 변환
        signal = np.array(ppg_data_list, dtype=np.float64)

        # 신호 처리
        out = ppg.ppg(signal=signal, sampling_rate=50., show=False)

        if len(out['peaks']) >= 2:
            # 피크 간 시간 간격을 계산하여 심박수 추정
            diff = (out['peaks'][1] - out['peaks'][0]) / 50.0  # 시간 간격 계산
            heart_rate = 60.0 / diff  # 심박수 계산
        else:
            heart_rate = None

        response = {
            'ts': out['ts'].tolist(),
            'filtered': out['filtered'].tolist(),
            'peaks': out['peaks'].tolist(),
            'heart_rate': heart_rate
        }

        # 클라이언트에게 데이터 전송
        socketio.emit('ppg_data', response)

        # 처리가 끝난 후 데이터 리스트 초기화
        ppg_data_list = []

    except Exception as e:
        print(f"Error processing PPG data: {e}")

@socketio.on('reset_data')
def handle_reset_data():
    global ppg_data_list
    print("Resetting PPG data...")
    ppg_data_list = []

if __name__ == '__main__':
    mqtt_client.loop_start()
    socketio.run(app, host='0.0.0.0', port=5000)