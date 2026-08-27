const net = require('node:net');
const originalListen = net.Server.prototype.listen;
net.Server.prototype.listen = function (...args) {
  const idx = args.findIndex((v) => v === '0.0.0.0');
  if (idx !== -1) args[idx] = '127.0.0.1';
  return originalListen.apply(this, args);
};
