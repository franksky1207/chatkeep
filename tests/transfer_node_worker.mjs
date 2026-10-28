/* Node worker-thread shim for the isolated browser worker's pure preparation. */
import {parentPort} from 'node:worker_threads';
globalThis.self=globalThis;
self.postMessage=data=>parentPort.postMessage({...data,worker_metrics:process.memoryUsage()});
await import('../docs/local-backup/transfer-worker.mjs');
parentPort.on('message',data=>self.onmessage({data}));
