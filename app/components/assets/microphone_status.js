export default function() {
  if (typeof MediaRecorder === 'undefined') return () => {};
  let starting = false, indicator, input;
  const originalStart = MediaRecorder.prototype.start;
  const media = navigator.mediaDevices;
  const originalGetUserMedia = media && media.getUserMedia;
  function clear() {
    starting = false;
    if (indicator) indicator.remove();
    indicator = undefined;
  }
  function show(text) {
    if (!input) return;
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.setAttribute('role', 'status');
      indicator.setAttribute('aria-live', 'polite');
      Object.assign(indicator.style, {
        position: 'absolute', inset: '0', zIndex: '5', borderRadius: '12px',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--st-secondary-background-color, #eee)',
        color: 'var(--st-text-color, #222)', fontSize: '14px', pointerEvents: 'none'
      });
      input.style.position = 'relative';
      input.appendChild(indicator);
    }
    indicator.textContent = text;
  }
  function click(event) {
    const target = event.target.closest && event.target.closest('button');
    if (!target) return;
    const id = target.getAttribute('data-testid');
    if (id === 'stChatInputMicButton') {
      if (starting) { event.preventDefault(); event.stopImmediatePropagation(); return; }
      clear();
      input = target.closest('[data-testid="stChatInput"]');
      starting = true;
      show('Starting microphone… Please wait before speaking.');
    } else if (id === 'stChatInputCancelButton' || id === 'stChatInputApproveButton') clear();
  }
  MediaRecorder.prototype.start = function(...args) {
    if (starting) {
      this.addEventListener('start', () => {
        starting = false;
        show('● Recording — speak now');
        // Show the native waveform and controls once recording really starts.
        setTimeout(() => { if (indicator && !starting) clear(); }, 900);
      }, {once: true});
      this.addEventListener('error', clear, {once: true});
      this.addEventListener('stop', clear, {once: true});
    }
    try { return originalStart.apply(this, args); }
    catch (error) { clear(); throw error; }
  };
  if (originalGetUserMedia) {
    media.getUserMedia = async function(...args) {
      try { return await originalGetUserMedia.apply(this, args); }
      catch (error) { clear(); throw error; }
    };
  }
  document.addEventListener('click', click, true);
  return () => {
    clear();
    document.removeEventListener('click', click, true);
    MediaRecorder.prototype.start = originalStart;
    if (originalGetUserMedia) media.getUserMedia = originalGetUserMedia;
  };
}
