import React, { useState, useEffect } from 'react';
import { LineChart, Line, Scatter, CartesianGrid, XAxis, YAxis, Legend, ResponsiveContainer, Tooltip, Brush } from 'recharts';
import { io } from 'socket.io-client';
import './App.css';

const App = () => {
  const [heartRateData, setHeartRateData] = useState({
    timestamps: [],
    filteredPPG: [],
    ppgPeaks: [],
    heartRate: null,
    spo2: null
  });

  const [label, setLabel] = useState({
    age: '',
    species: '',
    weight: '',
    disease: '',
  });

  const [isLabelSet, setIsLabelSet] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const handleResetData = () => {
    setIsLabelSet(true);  // 라벨이 설정됨을 표시
    const socket = io('http://223.130.142.8:5000');
    socket.emit('reset_data', label);
  };

  const handleSaveData = () => {
    // Socket을 통해 Flask 서버로 데이터 저장 요청
    const socket = io('http://223.130.142.8:5000');
    socket.emit('save_data', label);
    setHeartRateData({
      timestamps: [],
      filteredPPG: [],
      ppgPeaks: [],
      heartRate: null,
      spo2: null
    });
    setLabel({
      age: '',
      species: '',
      weight: '',
      disease: ''
    });
    setIsLabelSet(false);  // 라벨이 설정되지 않음을 표시
  }

  useEffect(() => {
    const socket = io('http://223.130.142.8:5000');

    socket.on('ppg_data', (data) => {
      console.log('Received PPG data:', data);

      // 새로운 데이터를 기존 데이터에 추가하여 업데이트합니다.
      setHeartRateData(prevData => ({
        timestamps: [...prevData.timestamps, ...data.ts],
        filteredPPG: [...prevData.filteredPPG, ...data.filtered],
        ppgPeaks: [...prevData.ppgPeaks, ...data.peaks],
        heartRate: data.heart_rate,
        spo2: data.spo2
      }));

      // 데이터가 정상적으로 수신되면 에러 메시지 초기화
      setErrorMessage('');
    });

    socket.on('request_retake', (message) => {
      console.log("retake");
      setErrorMessage(message.message);
      setHeartRateData(prevState => ({
        ...prevState,
        spo2: "-"
    }));
    });

    socket.on('reset_server', (data) => {
      setLabel({
        age: data.age,
        species: data.species,
        weight: data.weight,
        disease: data.disease
      });
      setIsLabelSet(true);
    });

    socket.on('save_server', (data) => {
      setLabel({
        age: '',
        species: '',
        weight: '',
        disease: ''
      });
      setIsLabelSet(false);
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  // Scatter 데이터를 생성하는 함수
  const createScatterData = () => {
    const scatterData = heartRateData.ppgPeaks.map((peak, index) => ({
      x: heartRateData.timestamps[peak],
      y: heartRateData.filteredPPG[peak]
    }));
    return scatterData;
  };

  return (
    <div className='App'>
      <h1>Real-time heart rate graph</h1>
      <h2>{label.age}/{label.species}/{label.weight}/{label.disease}</h2>
      <h2>heart rate: {heartRateData.heartRate} bpm</h2>
      <h2>spo2: {heartRateData.spo2} %</h2>
      {errorMessage && <p style={{ color: 'red', fontSize: '24px', fontWeight: '700' }}>{errorMessage}</p>}
      <div style={{width: '90%', height: '400px'}}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={heartRateData.timestamps.map((timestamp, index) => ({ timestamp, filteredPPG: heartRateData.filteredPPG[index] }))}
            margin={{ top: 20, right: 30, left: 20, bottom: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" label={{ value: 'Time', position: 'insideBottomRight', offset: 0 }} />
            <YAxis label={{ value: 'Amplitude', angle: -90, position: 'insideLeft' }} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="filteredPPG" stroke="blue" dot={false} />
            {/* Scatter 컴포넌트를 사용하여 PPG 피크 표시 */}
            <Scatter data={createScatterData()} fill="green" shape="circle" />
            {/* Brush 컴포넌트를 사용하여 스크롤 가능 영역 설정 */}
            <Brush
              dataKey="timestamp"
              height={30}
              stroke="#8884d8"
              startIndex={Math.max(0, heartRateData.timestamps.length - 120)}
              domain={{ x: [heartRateData.timestamps[Math.max(0, heartRateData.timestamps.length - 120)], heartRateData.timestamps[heartRateData.timestamps.length - 1]] }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div>
        {!isLabelSet && (
          <>
            <input
              type="text"
              value={label.age}
              onChange={(e) => setLabel({ ...label, age: e.target.value })}
              placeholder="age"
            />
            <input
              type="text"
              value={label.species}
              onChange={(e) => setLabel({ ...label, species: e.target.value })}
              placeholder="species"
            />
            <input
              type="text"
              value={label.weight}
              onChange={(e) => setLabel({ ...label, weight: e.target.value })}
              placeholder="weight"
            />
            <input
              type="text"
              value={label.disease}
              onChange={(e) => setLabel({ ...label, disease: e.target.value })}
              placeholder="disease"
            />
            <button onClick={handleResetData}>submit</button>
          </>
        )}
        {isLabelSet && (
          <button onClick={handleSaveData}>save</button>
        )}
      </div>
    </div>
  );
};

export default App;
