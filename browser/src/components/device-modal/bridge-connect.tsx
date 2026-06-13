import { useEffect, useState } from 'react';
import { Button, Input } from 'antd';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import { useTranslation } from 'react-i18next';

import { bridgeUrlAtom, connectionModeAtom, serialStateAtom, videoStateAtom } from '@/jotai/device.ts';
import { device } from '@/libs/device';
import { WebSocketSerialPort } from '@/libs/device/websocket-serial-port.ts';
import { mjpegCamera } from '@/libs/media/mjpeg-camera.ts';
import * as storage from '@/libs/storage';

type BridgeConnectProps = {
  setErrMsg: (msg: string) => void;
  onDisconnect: () => void;
};

export const BridgeConnect = ({ setErrMsg, onDisconnect }: BridgeConnectProps) => {
  const { t } = useTranslation();

  const connectionMode = useAtomValue(connectionModeAtom);
  const [bridgeUrl, setBridgeUrl] = useAtom(bridgeUrlAtom);
  const [serialState, setSerialState] = useAtom(serialStateAtom);
  const setVideoState = useSetAtom(videoStateAtom);

  const [inputValue, setInputValue] = useState(bridgeUrl || storage.getBridgeUrl() || '');

  useEffect(() => {
    if (connectionMode !== 'bridge') return;
    const savedUrl = storage.getBridgeUrl();
    if (savedUrl && serialState === 'disconnected') {
      attemptConnect(savedUrl);
    }
  }, [connectionMode]);

  const attemptConnect = async (url: string) => {
    if (serialState === 'connecting') return;
    setSerialState('connecting');
    setErrMsg('');

    const wsUrl = url.startsWith('ws') ? `${url}/serial` : `ws://${url}/serial`;
    const videoUrl = url.startsWith('http') ? `${url}/video` : `http://${url}/video`;

    const port = new WebSocketSerialPort();
    try {
      await port.init({ url: wsUrl, onDisconnect: handleDisconnect });
      device.useBridgePort(port);

      mjpegCamera.open(videoUrl);
      setVideoState('connected');

      setBridgeUrl(url);
      storage.setBridgeUrl(url);
      storage.setConnectionMode('bridge');

      setSerialState('connected');
    } catch (err) {
      console.log(err);
      device.useLocalPort();
      setSerialState('disconnected');
      setVideoState('disconnected');
      setErrMsg(t('modal.bridgeFailed'));
    }
  };

  const handleConnect = () => {
    const url = inputValue.trim();
    if (!url) return;
    attemptConnect(url);
  };

  const handleDisconnect = () => {
    mjpegCamera.close();
    device.useLocalPort();
    onDisconnect();
  };

  const isConnected = serialState === 'connected';
  const isConnecting = serialState === 'connecting';

  return (
    <div className="flex w-[300px] flex-col gap-3">
      <Input
        placeholder={t('modal.bridgeUrl')}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onPressEnter={handleConnect}
        disabled={isConnected || isConnecting}
      />
      <Button
        type={isConnected ? 'primary' : 'default'}
        className="w-full"
        loading={isConnecting}
        onClick={handleConnect}
        disabled={isConnected}
      >
        {isConnecting ? t('modal.bridgeConnecting') : t('modal.connectBridge')}
      </Button>
    </div>
  );
};
