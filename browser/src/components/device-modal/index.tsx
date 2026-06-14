import { useEffect, useState } from 'react';
import { Modal, Segmented } from 'antd';
import { useAtom, useSetAtom } from 'jotai';
import { useTranslation } from 'react-i18next';

import {
  connectionModeAtom,
  serialStateAtom,
  videoDeviceIdAtom,
  videoStateAtom
} from '@/jotai/device.ts';
import { camera } from '@/libs/media/camera.ts';
import { mjpegCamera } from '@/libs/media/mjpeg-camera.ts';
import * as storage from '@/libs/storage';

import { BridgeConnect } from './bridge-connect';
import { SerialPort } from './serial-port';
import { Video } from './video';

export const DeviceModal = () => {
  const { t } = useTranslation();

  const [videoState, setVideoState] = useAtom(videoStateAtom);
  const [serialState, setSerialState] = useAtom(serialStateAtom);
  const [connectionMode, setConnectionMode] = useAtom(connectionModeAtom);
  const setVideoDeviceId = useSetAtom(videoDeviceIdAtom);

  const [isOpen, setIsOpen] = useState(false);
  const [errMsg, setErrMsg] = useState('');

  useEffect(() => {
    const savedMode = storage.getConnectionMode() ?? 'local';
    setConnectionMode(savedMode);
  }, []);

  useEffect(() => {
    if (videoState === 'connected') {
      if (serialState === 'notSupported' || serialState === 'connected') {
        setIsOpen(false);
        return;
      }
    }

    setIsOpen(true);
  }, [videoState, serialState]);

  const disconnect = () => {
    setSerialState('disconnected');
    setVideoState('disconnected');
    setVideoDeviceId('');
    camera.close();
    mjpegCamera.close();
  };

  const handleModeChange = (mode: 'local' | 'bridge') => {
    disconnect();
    setConnectionMode(mode);
    storage.setConnectionMode(mode);
    setErrMsg('');
  };

  return (
    <Modal open={isOpen} title={t('modal.title')} footer={null} closable={false} destroyOnHidden>
      <div className="flex flex-col items-center justify-center space-y-5 py-6">
        <Segmented
          options={[
            { label: t('modal.modeLocal'), value: 'local' },
            { label: t('modal.modeBridge'), value: 'bridge' }
          ]}
          value={connectionMode}
          onChange={handleModeChange}
        />

        {connectionMode === 'local' ? (
          <>
            <Video setErrMsg={setErrMsg} />
            <SerialPort setErrMsg={setErrMsg} onDisconnect={disconnect} />
          </>
        ) : (
          <BridgeConnect setErrMsg={setErrMsg} onDisconnect={disconnect} />
        )}

        {errMsg && <span className="text-xs text-red-500">{errMsg}</span>}
      </div>
    </Modal>
  );
};
