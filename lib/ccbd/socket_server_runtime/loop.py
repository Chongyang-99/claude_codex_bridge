from __future__ import annotations

import queue
import socket
import threading
import time

_ACCEPT_POLL_TIMEOUT_S = 0.2
_WORKER_JOIN_TIMEOUT_S = 2.0


def serve_forever(server, *, poll_interval: float = 0.2, on_tick=None) -> None:
    server.listen()
    interval = max(0.0, float(poll_interval))
    start_worker(server, interval=interval, on_tick=on_tick)
    try:
        while not server._stop_event.is_set():
            runtime_socket = server._server
            if runtime_socket is None:
                break
            runtime_socket.settimeout(_ACCEPT_POLL_TIMEOUT_S)
            try:
                conn, _ = runtime_socket.accept()
            except socket.timeout:
                if server._stop_event.is_set() or server._server is not runtime_socket:
                    break
                continue
            except OSError:
                break
            enqueue_connection(server, conn)
    finally:
        stop_worker(server)
    worker_error = getattr(server, '_worker_error', None)
    server._worker_error = None
    if worker_error is not None:
        raise worker_error


def start_worker(server, *, interval: float, on_tick) -> None:
    worker = getattr(server, '_worker_thread', None)
    if worker is not None and worker.is_alive():
        return
    worker = threading.Thread(
        target=worker_loop,
        args=(server,),
        kwargs={'interval': interval, 'on_tick': on_tick},
        name='ccbd-socket-worker',
        daemon=True,
    )
    server._worker_error = None
    server._worker_thread = worker
    worker.start()


def stop_worker(server) -> None:
    worker = getattr(server, '_worker_thread', None)
    if worker is None:
        return
    close_pending_connections(server)
    try:
        server._connection_queue.put_nowait(server._worker_sentinel)
    except Exception:
        pass
    if worker is not threading.current_thread():
        worker.join(timeout=_WORKER_JOIN_TIMEOUT_S)
    if not worker.is_alive():
        server._worker_thread = None


def enqueue_connection(server, conn) -> None:
    if server._stop_event.is_set():
        try:
            conn.close()
        except OSError:
            pass
        return
    server._connection_queue.put(conn)


def close_pending_connections(server) -> None:
    while True:
        try:
            conn = server._connection_queue.get_nowait()
        except queue.Empty:
            return
        if conn is server._worker_sentinel:
            continue
        try:
            conn.close()
        except OSError:
            pass


def worker_loop(server, *, interval: float, on_tick) -> None:
    next_tick_at = time.monotonic() + interval
    try:
        while True:
            timeout = next_timeout(next_tick_at=next_tick_at, on_tick=on_tick)
            try:
                conn = server._connection_queue.get(timeout=timeout)
            except queue.Empty:
                if server._stop_event.is_set():
                    break
                next_tick_at = run_tick_if_needed(on_tick=on_tick, next_tick_at=next_tick_at, interval=interval)
                continue
            if conn is server._worker_sentinel:
                break
            handled_op = handle_worker_connection(server, conn)
            if server._stop_event.is_set():
                continue
            next_tick_at = post_request_tick(
                handled_op=handled_op,
                on_tick=on_tick,
                next_tick_at=next_tick_at,
                interval=interval,
                mutating_ops=server._MUTATING_OPS,
                double_tick_ops=server._DOUBLE_TICK_OPS,
            )
    except Exception as exc:
        server._worker_error = exc
        server._stop_event.set()


def handle_worker_connection(server, conn) -> str | None:
    try:
        with conn:
            return server._handle_connection(conn)
    except Exception:
        return None


def next_timeout(*, next_tick_at: float, on_tick) -> float | None:
    if on_tick is None:
        return _ACCEPT_POLL_TIMEOUT_S
    return max(0.0, next_tick_at - time.monotonic())


def run_tick_if_needed(*, on_tick, next_tick_at: float, interval: float) -> float:
    if on_tick is None:
        return next_tick_at
    on_tick()
    return time.monotonic() + interval


def post_request_tick(
    *,
    handled_op: str | None,
    on_tick,
    next_tick_at: float,
    interval: float,
    mutating_ops,
    double_tick_ops,
) -> float:
    if on_tick is not None and handled_op in mutating_ops:
        on_tick()
        if handled_op in double_tick_ops:
            on_tick()
        return time.monotonic() + interval
    if on_tick is not None and time.monotonic() >= next_tick_at:
        on_tick()
        return time.monotonic() + interval
    return next_tick_at


__all__ = [
    'close_pending_connections',
    'enqueue_connection',
    'handle_worker_connection',
    'next_timeout',
    'post_request_tick',
    'run_tick_if_needed',
    'serve_forever',
    'start_worker',
    'stop_worker',
    'worker_loop',
]
