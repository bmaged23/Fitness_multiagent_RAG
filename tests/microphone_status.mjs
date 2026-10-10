import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const js = readFileSync(new URL('../app/components/assets/microphone_status.js', import.meta.url), 'utf8');
const {default: mount} = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'));
let clickHandler, overlay, requested = false;
const input = {style: {}, appendChild(node) {overlay = node;}};
const button = {getAttribute: () => 'stChatInputMicButton', closest: () => input};
globalThis.document = {
 addEventListener(name, handler) {clickHandler = handler;}, removeEventListener() {},
 createElement() {return {style: {}, setAttribute() {}, remove() {overlay = null;}};}
};
Object.defineProperty(globalThis, 'navigator', {value: {mediaDevices: {async getUserMedia() {requested = true; return {};}}}, configurable: true});
globalThis.MediaRecorder = class {
 handlers = {};
 addEventListener(name, callback) {this.handlers[name] = callback;}
 start() {}
};
const original = MediaRecorder.prototype.start;
const dispose = mount();
clickHandler({target: {closest: () => button}});
assert.match(overlay.textContent, /Starting microphone/);
const recorder = new MediaRecorder();
recorder.start();
assert.match(overlay.textContent, /Starting microphone/, 'Starting alone must not claim to record');
recorder.handlers.start();
assert.match(overlay.textContent, /Recording — speak now/);
recorder.handlers.stop();
assert.equal(overlay, null);
dispose();
assert.equal(MediaRecorder.prototype.start, original);
console.log('Inline mic waits for recorder start, keeps position, and cleans up correctly.');
