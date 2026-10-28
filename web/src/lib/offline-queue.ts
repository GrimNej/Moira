// Saves made offline wait in IndexedDB and are sent when the connection returns (§4.3.8).
// Falls back to memory when IndexedDB is blocked; nothing here is shared with other viewers.

export interface QueuedSave {
  kind: 'text';
  text: string;
}

const DB = 'moira';
const STORE = 'outbox';
let memory: QueuedSave[] = [];

function open(): Promise<IDBDatabase | null> {
  return new Promise((resolve) => {
    try {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { autoIncrement: true });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

export async function enqueue(item: QueuedSave): Promise<void> {
  const db = await open();
  if (!db) {
    memory.push(item);
    return;
  }
  await new Promise<void>((resolve) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).add(item);
    tx.oncomplete = () => resolve();
    tx.onerror = () => resolve();
  });
}

async function all(db: IDBDatabase): Promise<[IDBValidKey, QueuedSave][]> {
  return new Promise((resolve) => {
    const out: [IDBValidKey, QueuedSave][] = [];
    const req = db.transaction(STORE).objectStore(STORE).openCursor();
    req.onsuccess = () => {
      const c = req.result;
      if (!c) return resolve(out);
      out.push([c.key, c.value as QueuedSave]);
      c.continue();
    };
    req.onerror = () => resolve(out);
  });
}

export async function pending(): Promise<number> {
  const db = await open();
  return db ? (await all(db)).length : memory.length;
}

export async function flush(send: (item: QueuedSave) => Promise<void>): Promise<number> {
  const db = await open();
  let sent = 0;
  if (!db) {
    const left: QueuedSave[] = [];
    for (const item of memory) {
      try {
        await send(item);
        sent++;
      } catch {
        left.push(item);
      }
    }
    memory = left;
    return sent;
  }
  for (const [key, item] of await all(db)) {
    try {
      await send(item);
      await new Promise<void>((resolve) => {
        const tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).delete(key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      });
      sent++;
    } catch {
      break; // still offline: keep the rest in order
    }
  }
  return sent;
}
