import React, { useState, useEffect } from 'react';
import { LineChart, Line, Scatter, CartesianGrid, XAxis, YAxis, Legend, ResponsiveContainer, Tooltip, Brush } from 'recharts';
import { io } from 'socket.io-client';

const App = () => {
  const [heartRateData, setHeartRateData] = useState({
    timestamps: [],
    filteredPPG: [],
    ppgPeaks: [],
    heartRate: null
  });

  useEffect(() => {
    const socket = io('http://localhost:5000');

    socket.on('ppg_data', (data) => {
      console.log('Received PPG data:', data);

      setHeartRateData({
        timestamps: data.ts,
        filteredPPG: data.filtered,
        ppgPeaks: data.peaks,
        heartRate: data.heart_rate
      });
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
    <div>
      <h1>실시간 심박수 그래프</h1>
      <h2>심박수: {heartRateData.heartRate} bpm</h2>
      <div style={{ width: '1400px', height: '400px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={heartRateData.timestamps.map((timestamp, index) => ({ timestamp, filteredPPG: heartRateData.filteredPPG[index] }))}
            margin={{ top: 20, right: 30, left: 20, bottom: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" label={{ value: '시간', position: 'insideBottomRight', offset: 0 }} />
            <YAxis label={{ value: '진폭', angle: -90, position: 'insideLeft' }} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="filteredPPG" stroke="blue" dot={false} />
            {/* Scatter 컴포넌트를 사용하여 PPG 피크 표시 */}
            <Scatter data={createScatterData()} fill="green" shape="circle" />
            {/* Brush 컴포넌트를 사용하여 스크롤 가능 영역 설정 */}
            <Brush dataKey="timestamp" height={30} stroke="#8884d8" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default App;
