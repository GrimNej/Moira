// Voice notes from the browser (§4.3.8): MediaRecorder (WebM/Opus on Chrome, MP4/AAC on Safari),
// up to 3 minutes. Some Telegram webviews have no microphone: the caller then says so.

export const MAX_MS = 3 * 60_000;

export function canRecord(): boolean {
  return typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
}

export interface Recording {
  stop(): Promise<Blob>;
  cancel(): void;
}

export async function startRecording(): Promise<Recording> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const type = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find((t) =>
    MediaRecorder.isTypeSupported(t),
  );
  const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
  const chunks: Blob[] = [];
  rec.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data);
  };
  rec.start(1000);
  const timer = window.setTimeout(() => {
    if (rec.state === 'recording') rec.stop();
  }, MAX_MS);
  const finish = (): void => {
    clearTimeout(timer);
    stream.getTracks().forEach((t) => t.stop());
  };
  return {
    stop: () =>
      new Promise<Blob>((resolve) => {
        rec.onstop = () => {
          finish();
          resolve(new Blob(chunks, { type: rec.mimeType || 'audio/webm' }));
        };
        if (rec.state === 'recording') rec.stop();
        else rec.onstop?.(new Event('stop'));
      }),
    cancel: () => {
      if (rec.state === 'recording') rec.stop();
      finish();
    },
  };
}
