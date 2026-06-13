import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";

let _doc: Y.Doc | null = null;
let _provider: WebsocketProvider | null = null;
let _port: number | null = null;

export function getYjsPort(): number | null {
  return _port;
}

export function setYjsPort(port: number): void {
  _port = port;
}

export function getYjsDoc(): Y.Doc {
  if (!_doc) {
    _doc = new Y.Doc();
  }
  return _doc;
}

export function connectYjsProvider(port: number, roomId: string): WebsocketProvider {
  if (_provider) {
    _provider.destroy();
  }
  _port = port;
  const doc = getYjsDoc();
  _provider = new WebsocketProvider(
    `ws://localhost:${port}`,
    roomId,
    doc
  );
  return _provider;
}

export function getYjsProvider(): WebsocketProvider | null {
  return _provider;
}

export function destroyYjs(): void {
  _provider?.destroy();
  _doc?.destroy();
  _doc = null;
  _provider = null;
}
