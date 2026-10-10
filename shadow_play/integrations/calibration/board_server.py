#!/usr/bin/env python3
"""Zynq PS JSON-line service. Actual hardware access lives in a supplied adapter."""
import argparse
import copy
import importlib.util
import json
import math
from pathlib import Path
import re
import socketserver
import sys
from tcp_bridge import MAX_BYTES, parse_json


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def indexed(items, key):
    require(isinstance(items, list) and bool(items), 'missing ' + key + ' list')
    result = {}
    for item in items:
        require(isinstance(item, dict), 'invalid list item')
        name = item.get(key)
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_-]+', name), 'invalid ID')
        require(name not in result, 'duplicate ID: ' + name)
        result[name] = item
    return result


def validate_config(config):
    require(type(config.get('version')) is int and config['version'] == 1 and config.get('simulation_only') is False,
            'real version 1 configuration required')
    require(config.get('reference_view') in ('front', 'rear'), 'invalid reference_view')
    for name in ('width_mm', 'height_mm'):
        value = config.get('stage', {}).get(name)
        require(number(value) and value > 0, 'measure stage ' + name)
    axes = indexed(config.get('axes'), 'id')
    slides = indexed(config.get('slides'), 'id')
    for item in list(axes.values()) + list(slides.values()):
        require(isinstance(item.get('unit'), str) and item['unit'] not in ('', 'demo', 'UNCONFIRMED'),
                'set actual unit for ' + item['id'])
        axis = item['id'] in axes and item is axes[item['id']]
        initial = item.get('initial' if axis else 'value')
        require(number(initial), 'set initial/value for ' + item['id'])
        require(type(item.get('controllable', False)) is bool, 'invalid controllable')
        if not axis:
            require(item.get('state_kind') in ('commanded', 'measured', 'fixed_assumption'), 'invalid slide state_kind')
            if item['state_kind'] == 'fixed_assumption':
                require(not item.get('controllable') and bool(item.get('assumption')), 'invalid fixed slide')
        if axis or item.get('controllable'):
            require(all(number(item.get(k)) for k in ('min', 'max', 'jog_step', 'max_step')),
                    'fill measured limits/steps for ' + item['id'])
            require(item['min'] < item['max'] and item['min'] <= initial <= item['max'] and
                    0 < item['jog_step'] <= item['max_step'], 'invalid limits for ' + item['id'])
    return axes, slides


class Controller:
    def __init__(self, config, driver):
        self.axes, self.slides = validate_config(config)
        self.version = 2 if any(s.get('controllable') for s in self.slides.values()) else 1
        self.driver = driver
        self.cache = {}
        self.last_seq = {}
        self.owner = None
        self.synced = False

    def values(self, items, specs, key, feedback=False):
        result = indexed(items, key)
        require(set(result) <= set(specs) if feedback else set(result) == set(specs), 'ID set mismatch')
        for name, item in result.items():
            spec = specs[name]
            require(item.get('unit') == spec['unit'] and number(item.get('value')), 'unit/value mismatch: ' + name)
            if not feedback and 'min' in spec:
                require(spec['min'] <= item['value'] <= spec['max'], 'outside limits: ' + name)
            if key == 'id':
                require(item.get('state_kind') == spec['state_kind'], 'slide state_kind mismatch: ' + name)
                require(item.get('controllable', spec.get('controllable', False)) == spec.get('controllable', False),
                        'slide controllable mismatch: ' + name)
                if spec['state_kind'] == 'fixed_assumption':
                    require(item.get('assumption') == spec['assumption'] and item['value'] == spec['value'],
                            'fixed slide condition changed: ' + name)
        return result

    def state(self, state):
        require(isinstance(state, dict), 'driver must return state dictionary')
        require(set(state) == {'adopted', 'slides', 'feedback'}, 'driver state needs adopted, slides, feedback only')
        self.values(state['adopted'], self.axes, 'axis_id')
        self.values(state['slides'], self.slides, 'id')
        if state['feedback'] is not None:
            self.values(state['feedback'], self.axes, 'axis_id', feedback=True)
        return copy.deepcopy(state)

    def handle(self, req):
        require(isinstance(req, dict), 'request must be object')
        require(type(req.get('version')) is int and req['version'] == self.version, 'protocol version mismatch')
        session, seq = req.get('session_id'), req.get('seq')
        require(isinstance(session, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', session), 'invalid session')
        require(type(seq) is int and seq > 0, 'invalid sequence')
        key = (session, seq)
        encoded = json.dumps(req, sort_keys=True, allow_nan=False)
        if key in self.cache:
            old, ack = self.cache[key]
            require(encoded == old, 'sequence reused with different content')
            return copy.deepcopy(ack)
        require(len(self.cache) < 10000, 'request limit reached; restart service and create NEW GUI session')
        require(seq > self.last_seq.get(session, 0), 'stale sequence')
        self.last_seq[session] = seq
        ack = {'version': req['version'], 'type': 'capture_ack', 'session_id': session, 'seq': seq,
               'accepted': False, 'adopted': [], 'feedback': None, 'slides': [], 'fault': None}
        try:
            require(set(req) == {'version', 'type', 'session_id', 'seq', 'axes'} |
                    ({'slides'} if self.version == 2 else set()), 'unexpected/missing request fields')
            kind = req['type']
            require(kind in ('capture_sync', 'capture_target'), 'invalid request type')
            targets = self.values(req['axes'], self.axes, 'axis_id')
            slide_targets = self.values(req['slides'], self.slides, 'id') if self.version == 2 else {}
            require(self.owner in (None, session), 'another GUI session owns service; close it before restarting service')
            before = self.state(self.driver.read_state())
            if kind == 'capture_sync':
                # NEVER apply the initial values carried by a sync request.
                self.owner, self.synced = session, True
                after = before
            else:
                require(self.synced and self.owner == session, 'fresh read-only sync required')
                for field, target, specs, id_key in (
                    ('adopted', targets, self.axes, 'axis_id'),
                    ('slides', slide_targets, self.slides, 'id'),
                ):
                    old = {v[id_key]: v for v in before[field]}
                    for name, item in target.items():
                        if field == 'slides' and not specs[name].get('controllable'):
                            require(item['value'] == old[name]['value'], 'noncontrolled slide changed')
                            continue
                        require(abs(item['value'] - old[name]['value']) <= specs[name]['max_step'] + 1e-9,
                                'step too large: ' + name)
                # Adapter must validate the complete group before any output and
                # return actual last-submitted values, including quantization.
                after = self.state(self.driver.apply_targets(copy.deepcopy(req['axes']),
                    [copy.deepcopy(s) for s in slide_targets.values() if self.slides[s['id']].get('controllable')]))
            ack.update(after)
            ack['accepted'] = True
        except Exception as error:
            self.synced = False
            ack['fault'] = str(error)
        # Including failures: replaying the same seq must never execute twice.
        self.cache[key] = (encoded, copy.deepcopy(ack))
        return ack


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(4)
        try:
            line = self.rfile.readline(MAX_BYTES + 1)
            require(len(line) <= MAX_BYTES and line.endswith(b'\n'), 'oversized/incomplete request')
            req = parse_json(line.decode('utf-8'))
            ack = self.server.controller.handle(req)
            self.server.log.write(json.dumps({'request': req, 'ack': ack}, ensure_ascii=False, allow_nan=False) + '\n')
            self.server.log.flush()
            self.wfile.write((json.dumps(ack, allow_nan=False) + '\n').encode('utf-8'))
        except Exception as error:
            print('Request failed (no automatic retry): ' + str(error), file=sys.stderr, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--adapter', type=Path, help='module implementing create_driver(config)')
    parser.add_argument('--bind', default='127.0.0.1', help='use board LAN IP for PC access')
    parser.add_argument('--port', type=int, default=7000)
    parser.add_argument('--log', type=Path, default=Path('board-capture.jsonl'))
    parser.add_argument('--check-config', action='store_true')
    args = parser.parse_args()
    config = parse_json(args.config.read_text(encoding='utf-8-sig'))
    validate_config(config)
    if args.check_config:
        print('Configuration values valid; hardware mapping/motion NOT verified.')
        return
    require(args.adapter is not None and 1 <= args.port <= 65535, 'adapter and valid port required')
    spec = importlib.util.spec_from_file_location('shadow_board_adapter', str(args.adapter.resolve()))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    controller = Controller(config, module.create_driver(copy.deepcopy(config)))
    controller.state(controller.driver.read_state())  # fail at startup if driver is uninitialized
    with args.log.open('a', encoding='utf-8') as log, socketserver.TCPServer((args.bind, args.port), Handler) as server:
        server.controller, server.log = controller, log
        print('Board service ready; one GUI session only; ACK means submitted, not arrived.', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Server stopped; motor stop/hold policy is the hardware driver responsibility.')
    except Exception as error:
        sys.exit(str(error))
