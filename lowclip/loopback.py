"""Desktop sound capture (WASAPI loopback) -> raw PCM -> ffmpeg over a local TCP socket.

WASAPI loopback delivers NO data while nothing is playing. To keep audio and video in sync
we pad those gaps with silence, so ffmpeg always sees a steady audio clock.
"""
import queue
import socket
import threading
import time


def list_output_devices():
    """Names of playback devices that can be captured (loopback)."""
    try:
        import pyaudiowpatch as pa
    except ImportError:
        return []
    p = pa.PyAudio()
    try:
        return [d["name"] for d in p.get_loopback_device_info_generator()]
    except Exception:
        return []
    finally:
        p.terminate()


def _pick_device(p, wanted):
    import pyaudiowpatch as pa
    if wanted:
        for d in p.get_loopback_device_info_generator():
            if d["name"] == wanted:
                return d
    wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
    spk = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if spk.get("isLoopbackDevice"):
        return spk
    for lb in p.get_loopback_device_info_generator():
        if spk["name"] in lb["name"]:
            return lb
    raise RuntimeError("no loopback device found for the default speakers")


class LoopbackFeeder:
    def __init__(self, device_name=""):
        self.device_name = device_name
        self.rate = 48000
        self.channels = 2
        self.port = 0
        self._bpf = 4
        self._q = queue.Queue(maxsize=500)
        self._stop_evt = threading.Event()
        self._threads = []
        self._p = None
        self._stream = None
        self._srv = None

    def prepare(self):
        """Open the device and a local listening socket. Returns (rate, channels, port)."""
        import pyaudiowpatch as pa
        self._p = pa.PyAudio()
        try:
            dev = _pick_device(self._p, self.device_name)
            self.rate = int(dev["defaultSampleRate"])
            self.channels = max(1, int(dev["maxInputChannels"]))
            self._bpf = 2 * self.channels

            def cb(in_data, frame_count, time_info, status):
                try:
                    self._q.put_nowait(in_data)
                except queue.Full:
                    pass
                return (None, pa.paContinue)

            self._stream = self._p.open(
                format=pa.paInt16, channels=self.channels, rate=self.rate,
                frames_per_buffer=self.rate // 50, input=True,
                input_device_index=dev["index"], stream_callback=cb)
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            self._srv = srv
            self.port = srv.getsockname()[1]
        except Exception:
            self.stop()
            raise
        return self.rate, self.channels, self.port

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        self._threads.append(t)

    def _run(self):
        srv = self._srv
        srv.settimeout(0.5)
        conn = None
        deadline = time.monotonic() + 30
        while conn is None and not self._stop_evt.is_set() and time.monotonic() < deadline:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
        if conn is None:
            return
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self._send_loop(conn)

    def _send_loop(self, conn):
        rate, bpf = self.rate, self._bpf
        while True:  # drop anything captured before ffmpeg connected
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        t0 = time.monotonic()
        sent = 0  # frames
        try:
            while not self._stop_evt.is_set():
                try:
                    data = self._q.get(timeout=0.02)
                    conn.sendall(data)
                    sent += len(data) // bpf
                    continue
                except queue.Empty:
                    pass
                deficit = int((time.monotonic() - t0) * rate) - sent
                if deficit > rate // 20:  # more than 50 ms without data -> pad silence
                    n = min(deficit, rate)
                    conn.sendall(bytes(n * bpf))
                    sent += n
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def stop(self):
        self._stop_evt.set()
        for t in self._threads:
            t.join(1)
        self._threads = []
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._srv is not None:
            try:
                self._srv.close()
            except OSError:
                pass
            self._srv = None
        if self._p is not None:
            try:
                self._p.terminate()
            except Exception:
                pass
            self._p = None
