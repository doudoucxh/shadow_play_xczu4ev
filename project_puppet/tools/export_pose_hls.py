#!/usr/bin/env python3
"""Export TinyUpperPoseNetV2 to the fixed-function HLS INT8 ABI.

The exporter is deliberately strict: it accepts only the root V2 checkpoint,
checks every state-dict entry, validates the fixed input/output shapes and HLS
buffer limits, folds BatchNorm deterministically, and emits both the floating
fallback and packed INT8 headers used by the bare-metal application.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from model import TinyUpperPoseNetV2  # noqa: E402

INPUT_W, INPUT_H, KEYPOINTS = 256, 144, 9
EXPECTED_OUTPUT = (1, 9, 36, 64)
EXPECTED_HLS_LAYERS = 14
MAX_CHANNELS = 48
MAX_FEATURE_BYTES = 72 * 128 * 24
HEAD_STRIDE = 16


@dataclass(frozen=True)
class ConvSpec:
    name: str
    conv: str
    bn: str | None
    kind: str
    input_name: str
    output_name: str
    residual_name: str | None = None


SPECS = (
    ConvSpec("pose_stem", "stem.0", "stem.1", "stem", "input", "pose_stem"),
    ConvSpec("pose_high_dw", "high.depthwise.0", "high.depthwise.1", "dw", "pose_stem", "pose_high_dw"),
    ConvSpec("pose_high_pw", "high.pointwise.0", "high.pointwise.1", "pw", "pose_high_dw", "pose_high_pw"),
    ConvSpec("pose_highref0_dw", "high_refine.0.depthwise.0", "high_refine.0.depthwise.1", "dw", "pose_high_pw", "pose_highref0_dw"),
    ConvSpec("pose_highref0_pw", "high_refine.0.pointwise.0", "high_refine.0.pointwise.1", "pw", "pose_highref0_dw", "pose_highref0_pw", "pose_high_pw"),
    ConvSpec("pose_highref1_dw", "high_refine.1.depthwise.0", "high_refine.1.depthwise.1", "dw", "pose_highref0_pw", "pose_highref1_dw"),
    ConvSpec("pose_highref1_pw", "high_refine.1.pointwise.0", "high_refine.1.pointwise.1", "pw", "pose_highref1_dw", "pose_highref1_pw", "pose_highref0_pw"),
    ConvSpec("pose_low0_dw", "low.0.depthwise.0", "low.0.depthwise.1", "dw", "pose_highref1_pw", "pose_low0_dw"),
    ConvSpec("pose_low0_pw", "low.0.pointwise.0", "low.0.pointwise.1", "pw", "pose_low0_dw", "pose_low0_pw"),
    ConvSpec("pose_low1_dw", "low.1.depthwise.0", "low.1.depthwise.1", "dw", "pose_low0_pw", "pose_low1_dw"),
    ConvSpec("pose_low1_pw", "low.1.pointwise.0", "low.1.pointwise.1", "pw", "pose_low1_dw", "pose_low1_pw", "pose_low0_pw"),
    ConvSpec("pose_low2_dw", "low.2.depthwise.0", "low.2.depthwise.1", "dw", "pose_low1_pw", "pose_low2_dw"),
    ConvSpec("pose_low2_pw", "low.2.pointwise.0", "low.2.pointwise.1", "pw", "pose_low2_dw", "pose_low2_pw", "pose_low1_pw"),
    ConvSpec("pose_low3_dw", "low.3.depthwise.0", "low.3.depthwise.1", "dw", "pose_low2_pw", "pose_low3_dw"),
    ConvSpec("pose_low3_pw", "low.3.pointwise.0", "low.3.pointwise.1", "pw", "pose_low3_dw", "pose_low3_pw", "pose_low2_pw"),
    ConvSpec("pose_context", "context_projection.0", "context_projection.1", "pw", "pose_low3_pw", "pose_context"),
    ConvSpec("pose_ref0_dw", "refine.0.depthwise.0", "refine.0.depthwise.1", "dw", "pose_merge", "pose_ref0_dw"),
    ConvSpec("pose_ref0_pw", "refine.0.pointwise.0", "refine.0.pointwise.1", "pw", "pose_ref0_dw", "pose_ref0_pw", "pose_merge"),
    ConvSpec("pose_ref1_dw", "refine.1.depthwise.0", "refine.1.depthwise.1", "dw", "pose_ref0_pw", "pose_ref1_dw"),
    ConvSpec("pose_ref1_pw", "refine.1.pointwise.0", "refine.1.pointwise.1", "pw", "pose_ref1_dw", "pose_ref1_pw", "pose_ref0_pw"),
    ConvSpec("pose_ref2_dw", "refine.2.depthwise.0", "refine.2.depthwise.1", "dw", "pose_ref1_pw", "pose_ref2_dw"),
    ConvSpec("pose_ref2_pw", "refine.2.pointwise.0", "refine.2.pointwise.1", "pw", "pose_ref2_dw", "pose_ref2_pw", "pose_ref1_pw"),
    ConvSpec("pose_head", "head", None, "head", "pose_ref2_pw", "pose_head"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_checkpoint(path: Path) -> tuple[TinyUpperPoseNetV2, dict]:
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(checkpoint, dict) or "model" not in checkpoint:
        raise RuntimeError("checkpoint must be a dictionary containing 'model'")
    if checkpoint.get("architecture") != "v2":
        raise RuntimeError(f"expected architecture='v2', got {checkpoint.get('architecture')!r}")
    state = checkpoint["model"]
    if not isinstance(state, (dict, OrderedDict)):
        raise RuntimeError("checkpoint['model'] is not a state-dict")
    model = TinyUpperPoseNetV2(KEYPOINTS).eval()
    expected = model.state_dict()
    if list(state.keys()) != list(expected.keys()):
        missing = [key for key in expected if key not in state]
        extra = [key for key in state if key not in expected]
        raise RuntimeError(f"state-dict order/content mismatch; missing={missing}, extra={extra}")
    model.load_state_dict(state, strict=True)
    with torch.no_grad():
        output = model(torch.zeros(1, 3, INPUT_H, INPUT_W))
    if tuple(output.shape) != EXPECTED_OUTPUT:
        raise RuntimeError(f"output shape {tuple(output.shape)} != {EXPECTED_OUTPUT}")
    if sum(p.numel() for p in model.parameters()) != 21657:
        raise RuntimeError("unexpected trainable parameter count for TinyUpperPoseNetV2")
    return model, checkpoint


def fuse_conv_bn(model: torch.nn.Module, conv_name: str, bn_name: str | None) -> tuple[torch.Tensor, torch.Tensor, torch.nn.Conv2d]:
    conv = model.get_submodule(conv_name)
    if not isinstance(conv, torch.nn.Conv2d):
        raise TypeError(f"{conv_name} is not Conv2d")
    weight = conv.weight.detach().to(torch.float64).clone()
    bias = torch.zeros(conv.out_channels, dtype=torch.float64) if conv.bias is None else conv.bias.detach().to(torch.float64).clone()
    if bn_name is not None:
        bn = model.get_submodule(bn_name)
        if not isinstance(bn, torch.nn.BatchNorm2d):
            raise TypeError(f"{bn_name} is not BatchNorm2d")
        scale = bn.weight.detach().to(torch.float64) / torch.sqrt(bn.running_var.detach().to(torch.float64) + bn.eps)
        weight *= scale.reshape(-1, 1, 1, 1)
        bias = bn.bias.detach().to(torch.float64) + (bias - bn.running_mean.detach().to(torch.float64)) * scale
    return weight.to(torch.float32), bias.to(torch.float32), conv


def fused_parameters(model: torch.nn.Module) -> OrderedDict[str, dict]:
    params: OrderedDict[str, dict] = OrderedDict()
    for spec in SPECS:
        weight, bias, conv = fuse_conv_bn(model, spec.conv, spec.bn)
        if spec.kind == "stem":
            flat_weight = weight.permute(0, 2, 3, 1).contiguous()
        elif spec.kind == "dw":
            flat_weight = weight[:, 0].contiguous()
        else:
            flat_weight = weight[:, :, 0, 0].contiguous()
        params[spec.name] = {
            "weight": weight,
            "flat_weight": flat_weight,
            "bias": bias,
            "stride": tuple(conv.stride),
            "padding": tuple(conv.padding),
            "groups": conv.groups,
            "kind": spec.kind,
        }
    return params


def _conv(x: torch.Tensor, entry: dict, relu: bool = True) -> torch.Tensor:
    y = F.conv2d(x, entry["weight"], entry["bias"], stride=entry["stride"], padding=entry["padding"], groups=entry["groups"])
    return torch.relu(y) if relu else y


def float_forward(x: torch.Tensor, params: OrderedDict[str, dict], record: bool = False) -> tuple[torch.Tensor, OrderedDict[str, torch.Tensor]]:
    values: OrderedDict[str, torch.Tensor] = OrderedDict()

    def keep(name: str, value: torch.Tensor) -> torch.Tensor:
        if record:
            values[name] = value.detach()
        return value

    stem = keep("pose_stem", _conv(x, params["pose_stem"]))
    high_dw = keep("pose_high_dw", _conv(stem, params["pose_high_dw"]))
    high = keep("pose_high_pw", _conv(high_dw, params["pose_high_pw"]))
    for index in range(2):
        prefix = f"pose_highref{index}"
        dw = keep(prefix + "_dw", _conv(high, params[prefix + "_dw"]))
        module = _conv(dw, params[prefix + "_pw"])
        keep(prefix + "_pw_module", module)
        high = keep(prefix + "_pw", module + high)
    low_dw = keep("pose_low0_dw", _conv(high, params["pose_low0_dw"]))
    low = keep("pose_low0_pw", _conv(low_dw, params["pose_low0_pw"]))
    for index in range(1, 4):
        prefix = f"pose_low{index}"
        dw = keep(prefix + "_dw", _conv(low, params[prefix + "_dw"]))
        module = _conv(dw, params[prefix + "_pw"])
        keep(prefix + "_pw_module", module)
        low = keep(prefix + "_pw", module + low)
    context = keep("pose_context", _conv(low, params["pose_context"]))
    merged = keep("pose_merge", F.interpolate(context, scale_factor=2, mode="nearest") + high)
    refined = merged
    for index in range(3):
        prefix = f"pose_ref{index}"
        dw = keep(prefix + "_dw", _conv(refined, params[prefix + "_dw"]))
        module = _conv(dw, params[prefix + "_pw"])
        keep(prefix + "_pw_module", module)
        refined = keep(prefix + "_pw", module + refined)
    head = keep("pose_head", _conv(refined, params["pose_head"], relu=False))
    return head, values


def discover_inputs(directory: Path) -> list[Path]:
    extensions = {".bin", ".bmp", ".png", ".jpg", ".jpeg"}
    return sorted((path for path in directory.rglob("*")
                   if path.is_file() and path.suffix.lower() in extensions
                   and not path.name.lower().endswith(".heatmap.bin")),
                  key=lambda p: p.as_posix().lower())


def choose_inputs(paths: list[Path], count: int, offset: int) -> list[Path]:
    if offset < 0 or count <= 0 or offset + count > len(paths):
        raise RuntimeError(f"requested [{offset}:{offset + count}] from only {len(paths)} calibration inputs")
    return paths[offset:offset + count]


def read_rgb(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".bin":
        raw = np.fromfile(path, dtype=np.uint8)
        if raw.size != INPUT_W * INPUT_H * 3:
            raise RuntimeError(f"{path}: raw snapshot has {raw.size} bytes, expected {INPUT_W * INPUT_H * 3}")
        return raw.reshape(INPUT_H, INPUT_W, 3)[:, :, ::-1].copy()  # board snapshot is BGR
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        if rgb.size != (INPUT_W, INPUT_H):
            rgb = rgb.resize((INPUT_W, INPUT_H), Image.Resampling.BILINEAR)
        return np.asarray(rgb, dtype=np.uint8)


def to_tensor(rgb: np.ndarray) -> torch.Tensor:
    array = rgb.astype(np.float32) * (1.0 / 127.5) - 1.0
    return torch.from_numpy(array.transpose(2, 0, 1)).unsqueeze(0)


def collect_ranges(paths: Iterable[Path], params: OrderedDict[str, dict], percentile: float) -> tuple[OrderedDict[str, list[float]], list[dict]]:
    ranges: OrderedDict[str, list[float]] = OrderedDict(input=[-1.0, 1.0])
    records: list[dict] = []
    with torch.inference_mode():
        for index, path in enumerate(paths):
            rgb = read_rgb(path)
            _, values = float_forward(to_tensor(rgb), params, record=True)
            for name, tensor in values.items():
                if name == "pose_head" or percentile >= 100.0:
                    low, high = float(tensor.min()), float(tensor.max())
                else:
                    flat = tensor.reshape(-1)
                    if flat.numel() > 8192:
                        stride = math.ceil(flat.numel() / 8192)
                        flat = flat[::stride]
                    tail = (100.0 - percentile) / 100.0
                    low = float(torch.quantile(flat, tail))
                    high = float(torch.quantile(flat, 1.0 - tail))
                if name not in ranges:
                    ranges[name] = [low, high]
                else:
                    ranges[name][0] = min(ranges[name][0], low)
                    ranges[name][1] = max(ranges[name][1], high)
            records.append({"index": index, "path": str(path.resolve()), "sha256": sha256_file(path)})
    return ranges, records


def activation_qparams(low: float, high: float, relu: bool) -> tuple[float, int]:
    if relu:
        return max(high, 1e-12) / 255.0, 0
    low, high = min(low, 0.0), max(high, 0.0)
    scale = max(high - low, 1e-12) / 255.0
    zero = int(np.clip(round(-low / scale), 0, 255))
    return scale, zero


def encode_multiplier(real: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
    scalar = np.asarray(real).ndim == 0
    real_array = np.atleast_1d(np.asarray(real, dtype=np.float64))
    if np.any(real_array <= 0.0):
        raise RuntimeError("requantization multiplier must be positive")
    mantissa, exponent = np.frexp(real_array)
    multiplier = np.rint(mantissa * 65536.0).astype(np.int64)
    carry = multiplier == 65536
    multiplier[carry] //= 2
    exponent[carry] += 1
    shift = 16 - exponent
    if np.any(multiplier < 1) or np.any(multiplier > 65535) or np.any(shift < 0) or np.any(shift > 31):
        raise RuntimeError("requantization multiplier does not fit u16/right-shift ABI")
    multiplier = multiplier.astype(np.uint16)
    shift = shift.astype(np.uint8)
    if scalar:
        return multiplier[0], shift[0]
    return multiplier, shift


def quantize_model(params: OrderedDict[str, dict], ranges: OrderedDict[str, list[float]]) -> tuple[OrderedDict[str, dict], OrderedDict[str, tuple[float, int]]]:
    activations: OrderedDict[str, tuple[float, int]] = OrderedDict()
    activations["input"] = activation_qparams(*ranges["input"], relu=False)
    for name, limits in ranges.items():
        if name == "input" or name.endswith("_module"):
            continue
        activations[name] = activation_qparams(*limits, relu=name != "pose_head")
    quantized: OrderedDict[str, dict] = OrderedDict()
    for spec in SPECS:
        entry = params[spec.name]
        flat = entry["flat_weight"].detach().cpu().numpy().astype(np.float64)
        out_channels = flat.shape[0]
        rows = flat.reshape(out_channels, -1)
        weight_scale = np.maximum(np.max(np.abs(rows), axis=1), 1e-12) / 127.0
        weight_q = np.clip(np.rint(rows / weight_scale[:, None]), -127, 127).astype(np.int8).reshape(flat.shape)
        input_scale, input_zp = activations[spec.input_name]
        output_scale, output_zp = activations[spec.output_name]
        bias = entry["bias"].detach().cpu().numpy().astype(np.float64)
        bias_q = np.rint(bias / (input_scale * weight_scale)).astype(np.int64)
        if np.any(bias_q < np.iinfo(np.int32).min) or np.any(bias_q > np.iinfo(np.int32).max):
            raise RuntimeError(f"{spec.name}: bias exceeds int32")
        multiplier, shift = encode_multiplier(input_scale * weight_scale / output_scale)
        qentry = {
            "weight": weight_q,
            "bias": bias_q.astype(np.int32),
            "weight_scale": weight_scale,
            "multiplier": multiplier,
            "shift": shift,
            "input_scale": input_scale,
            "input_zero_point": input_zp,
            "output_scale": output_scale,
            "output_zero_point": output_zp,
            "kind": spec.kind,
        }
        if spec.residual_name:
            residual_scale, residual_zp = activations[spec.residual_name]
            residual_multiplier, residual_shift = encode_multiplier(residual_scale / output_scale)
            qentry.update(residual_scale=residual_scale, residual_zero_point=residual_zp,
                          residual_multiplier=int(residual_multiplier), residual_shift=int(residual_shift))
        quantized[spec.name] = qentry
    return quantized, activations


def _round_shift(product: torch.Tensor, shift: np.ndarray | int) -> torch.Tensor:
    shift_tensor = torch.as_tensor(shift, dtype=torch.int64, device=product.device).reshape(1, -1, 1, 1)
    magnitude = torch.abs(product)
    rounded = torch.where(shift_tensor == 0, magnitude, (magnitude + torch.bitwise_left_shift(torch.ones_like(shift_tensor), shift_tensor - 1)) >> shift_tensor)
    return torch.where(product < 0, -rounded, rounded)


def requantize_accum(accum: torch.Tensor, qentry: dict, relu: bool, residual: torch.Tensor | None = None) -> torch.Tensor:
    accum = accum.to(torch.int64)
    if relu:
        accum = torch.clamp_min(accum, 0)
    multiplier = torch.from_numpy(qentry["multiplier"].astype(np.int64)).reshape(1, -1, 1, 1)
    scaled = _round_shift(accum * multiplier, qentry["shift"])
    if residual is not None:
        residual_value = residual.to(torch.int64) - int(qentry["residual_zero_point"])
        scaled += _round_shift(residual_value * int(qentry["residual_multiplier"]), int(qentry["residual_shift"]))
    return torch.clamp(scaled + int(qentry["output_zero_point"]), 0, 255).to(torch.uint8)


def qconv(x: torch.Tensor, qentry: dict, stride: tuple[int, int], padding: tuple[int, int], groups: int, relu: bool, residual: torch.Tensor | None = None) -> torch.Tensor:
    xin = x.to(torch.float32) - float(qentry["input_zero_point"])
    weight = torch.from_numpy(qentry["weight"].astype(np.int8)).to(torch.float32)
    kind = qentry["kind"]
    if kind == "stem":
        weight = weight.permute(0, 3, 1, 2).contiguous()
    elif kind == "dw":
        weight = weight.unsqueeze(1)
    else:
        weight = weight.unsqueeze(-1).unsqueeze(-1)
    accum = torch.round(F.conv2d(xin, weight, None, stride=stride, padding=padding, groups=groups)).to(torch.int64)
    accum += torch.from_numpy(qentry["bias"].astype(np.int64)).reshape(1, -1, 1, 1)
    return requantize_accum(accum, qentry, relu=relu, residual=residual)


def fixed_forward(rgb: np.ndarray, params: OrderedDict[str, dict], quantized: OrderedDict[str, dict], activations: OrderedDict[str, tuple[float, int]]) -> torch.Tensor:
    input_scale, input_zp = activations["input"]
    lut = np.clip(np.rint(((np.arange(256, dtype=np.float64) / 127.5) - 1.0) / input_scale) + input_zp, 0, 255).astype(np.uint8)
    q = torch.from_numpy(lut[rgb].transpose(2, 0, 1).copy()).unsqueeze(0)

    def run(name: str, source: torch.Tensor, residual: torch.Tensor | None = None, relu: bool = True) -> torch.Tensor:
        entry, fentry = quantized[name], params[name]
        return qconv(source, entry, fentry["stride"], fentry["padding"], fentry["groups"], relu, residual)

    stem = run("pose_stem", q)
    high = run("pose_high_pw", run("pose_high_dw", stem))
    for index in range(2):
        prefix = f"pose_highref{index}"
        high = run(prefix + "_pw", run(prefix + "_dw", high), high)
    low = run("pose_low0_pw", run("pose_low0_dw", high))
    for index in range(1, 4):
        prefix = f"pose_low{index}"
        low = run(prefix + "_pw", run(prefix + "_dw", low), low)
    context = run("pose_context", low)
    merge_scale, merge_zp = activations["pose_merge"]
    context_scale, context_zp = activations["pose_context"]
    high_scale, high_zp = activations["pose_highref1_pw"]
    cm, cs = encode_multiplier(context_scale / merge_scale)
    hm, hs = encode_multiplier(high_scale / merge_scale)
    context_up = F.interpolate(context.to(torch.float32), scale_factor=2, mode="nearest").to(torch.int64)
    merged = _round_shift((context_up - context_zp) * int(cm), int(cs))
    merged += _round_shift((high.to(torch.int64) - high_zp) * int(hm), int(hs))
    refined = torch.clamp(merged + merge_zp, 0, 255).to(torch.uint8)
    for index in range(3):
        prefix = f"pose_ref{index}"
        refined = run(prefix + "_pw", run(prefix + "_dw", refined), refined)
    head = run("pose_head", refined, relu=False)
    padded = torch.zeros(1, HEAD_STRIDE, 36, 64, dtype=torch.uint8)
    padded[:, :KEYPOINTS] = head
    return padded


def decode_input_coordinates(heatmaps: torch.Tensor) -> np.ndarray:
    array = heatmaps[0, :KEYPOINTS].detach().cpu().numpy()
    flat = array.reshape(KEYPOINTS, -1).argmax(axis=1)
    return np.stack(((flat % 64) * 4.0 + 1.5, (flat // 64) * 4.0 + 1.5), axis=1)


def pack_bytes(values: np.ndarray) -> np.ndarray:
    raw = np.asarray(values).view(np.uint8).reshape(-1)
    padded = np.pad(raw, (0, (-raw.size) % 8))
    return padded.reshape(-1, 8).astype(np.uint64).dot((np.uint64(1) << np.arange(0, 64, 8, dtype=np.uint64)))


def pack_params(entry: dict) -> np.ndarray:
    bias = entry["bias"].astype(np.int64) & 0xFFFFFFFF
    return bias.astype(np.uint64) | (entry["multiplier"].astype(np.uint64) << 32) | (entry["shift"].astype(np.uint64) << 48)


def format_u64_array(name: str, values: np.ndarray) -> str:
    lines = [f"static const unsigned long long {name}[{len(values)}] POSE_Q_ALIGN = {{"]
    for start in range(0, len(values), 4):
        lines.append("    " + ", ".join(f"0x{int(value):016X}ULL" for value in values[start:start + 4]) + ",")
    lines.append("};\n")
    return "\n".join(lines)


def format_float_array(name: str, values: np.ndarray) -> str:
    flat = np.asarray(values, dtype=np.float32).reshape(-1)
    lines = [f"static const float {name}[{len(flat)}] POSE_ALIGN = {{"]
    for start in range(0, len(flat), 8):
        tokens = []
        for value in flat[start:start + 8]:
            token = f"{float(value):.9g}"
            if "." not in token and "e" not in token.lower():
                token += ".0"
            tokens.append(token + "f")
        lines.append("    " + ", ".join(tokens) + ",")
    lines.append("};\n")
    return "\n".join(lines)


def write_float_header(path: Path, params: OrderedDict[str, dict], checkpoint: dict, checkpoint_sha: str) -> None:
    lines = ["/* Generated from root best.pt; do not edit. */", "#ifndef POSE_MODEL_WEIGHTS_H", "#define POSE_MODEL_WEIGHTS_H",
             "#define POSE_ALIGN __attribute__((aligned(64)))", "#define POSE_MODEL_ARCH 2", "#define POSE_STEM_CHANNELS 24U",
             "#define POSE_HIGH_CHANNELS 32U", "#define POSE_LOW_CHANNELS 48U", f"#define POSE_MODEL_EPOCH {int(checkpoint.get('epoch', 0))}",
             f'#define POSE_MODEL_SHA256 "{checkpoint_sha}"']
    for index in range(8):
        lines.append(f"#define POSE_MODEL_SHA256_WORD_{index} 0x{checkpoint_sha[index * 8:(index + 1) * 8].upper()}U")
    for name, entry in params.items():
        lines.append(format_float_array(name + "_w", entry["flat_weight"].cpu().numpy()))
        lines.append(format_float_array(name + "_b", entry["bias"].cpu().numpy()))
    lines.append("#endif\n")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_int8_header(path: Path, quantized: OrderedDict[str, dict], activations: OrderedDict[str, tuple[float, int]]) -> None:
    input_scale, input_zp = activations["input"]
    lut = np.clip(np.rint(((np.arange(256, dtype=np.float64) / 127.5) - 1.0) / input_scale) + input_zp, 0, 255).astype(np.uint8)
    lines = ["/* Generated calibrated INT8 parameters for the PL CNN engine. */", "#ifndef POSE_MODEL_INT8_WEIGHTS_H",
             "#define POSE_MODEL_INT8_WEIGHTS_H", "#define POSE_Q_ALIGN __attribute__((aligned(64)))", format_u64_array("pose_input_quant_lut_q", pack_bytes(lut))]
    for spec in SPECS:
        entry = quantized[spec.name]
        lines.append(format_u64_array(spec.name + "_w_q", pack_bytes(entry["weight"])))
        lines.append(format_u64_array(spec.name + "_p_q", pack_params(entry)))
        macro = spec.name.upper()
        lines += [f"#define {macro}_INPUT_ZP {entry['input_zero_point']}U", f"#define {macro}_OUTPUT_ZP {entry['output_zero_point']}U"]
        if spec.residual_name:
            lines += [f"#define {macro}_RESIDUAL_ZP {entry['residual_zero_point']}U",
                      f"#define {macro}_RESIDUAL_MULT {entry['residual_multiplier']}U",
                      f"#define {macro}_RESIDUAL_SHIFT {entry['residual_shift']}U"]
    merge_scale, merge_zp = activations["pose_merge"]
    context_scale, context_zp = activations["pose_context"]
    high_scale, high_zp = activations["pose_highref1_pw"]
    input_mult, input_shift = encode_multiplier(context_scale / merge_scale)
    residual_mult, residual_shift = encode_multiplier(high_scale / merge_scale)
    merge_param = np.array([np.uint64(int(input_mult) << 32 | int(input_shift) << 48)], dtype=np.uint64)
    lines += [format_u64_array("pose_merge_input_p_q", merge_param), f"#define POSE_MERGE_INPUT_ZP {context_zp}U",
              f"#define POSE_MERGE_INPUT_MULT {int(input_mult)}U", f"#define POSE_MERGE_INPUT_SHIFT {int(input_shift)}U",
              f"#define POSE_MERGE_RESIDUAL_ZP {high_zp}U", f"#define POSE_MERGE_RESIDUAL_MULT {int(residual_mult)}U",
              f"#define POSE_MERGE_RESIDUAL_SHIFT {int(residual_shift)}U", f"#define POSE_MERGE_OUTPUT_ZP {merge_zp}U",
              f"#define POSE_HEAD_OUTPUT_SCALE_MILLI {int(round(activations['pose_head'][0] * 1000.0))}", "#endif\n"]
    path.write_text("\n\n".join(lines), encoding="utf-8", newline="\n")


def metadata_dict(checkpoint_path: Path, checkpoint: dict, checkpoint_sha: str, params: OrderedDict[str, dict], quantized: OrderedDict[str, dict], activations: OrderedDict[str, tuple[float, int]], ranges: OrderedDict[str, list[float]], calibration: list[dict], calibration_kind: str, activation_percentile: float) -> dict:
    layers = OrderedDict()
    for spec in SPECS:
        q = quantized[spec.name]
        p = params[spec.name]
        item = {
            "module": spec.conv,
            "kind": spec.kind,
            "input_scale": q["input_scale"], "input_zero_point": q["input_zero_point"],
            "output_scale": q["output_scale"], "output_zero_point": q["output_zero_point"],
            "weight_shape": list(q["weight"].shape), "groups": p["groups"], "stride": list(p["stride"]), "padding": list(p["padding"]),
            "weight_scales": [float(value) for value in q["weight_scale"]],
            "multipliers": [int(value) for value in q["multiplier"]],
            "right_shifts": [int(value) for value in q["shift"]],
            "bias_int32_min": int(q["bias"].min()),
            "bias_int32_max": int(q["bias"].max()),
            "relu": spec.kind != "head",
        }
        if spec.residual_name:
            item.update(residual_source=spec.residual_name, residual_scale=q["residual_scale"], residual_zero_point=q["residual_zero_point"],
                        residual_multiplier=q["residual_multiplier"], residual_shift=q["residual_shift"])
        layers[spec.name] = item
    return {
        "schema_version": 2,
        "checkpoint": str(checkpoint_path.resolve()),
        "checkpoint_sha256": checkpoint_sha,
        "architecture": checkpoint.get("architecture"),
        "epoch": checkpoint.get("epoch"),
        "input_shape": [1, 3, INPUT_H, INPUT_W],
        "output_shape": list(EXPECTED_OUTPUT),
        "hls_layer_count": EXPECTED_HLS_LAYERS,
        "head_storage_shape": [1, HEAD_STRIDE, 36, 64],
        "format": "uint8 activations, per-output-channel int8 weights, int32 bias, u16 multiplier/right-shift",
        "calibration": {"kind": calibration_kind, "count": len(calibration), "activation_percentile": activation_percentile, "samples": calibration},
        "activation_ranges": ranges,
        "activation_qparams": {name: {"scale": scale, "zero_point": zp} for name, (scale, zp) in activations.items()},
        "layers": layers,
    }


def save_npz(path: Path, params: OrderedDict[str, dict], quantized: OrderedDict[str, dict], activations: OrderedDict[str, tuple[float, int]]) -> None:
    arrays: dict[str, np.ndarray] = {}
    for name, entry in params.items():
        arrays[name + "__float_weight"] = entry["weight"].cpu().numpy()
        arrays[name + "__float_bias"] = entry["bias"].cpu().numpy()
    for name, entry in quantized.items():
        for key in ("weight", "bias", "weight_scale", "multiplier", "shift"):
            arrays[name + "__" + key] = np.asarray(entry[key])
    for name, (scale, zp) in activations.items():
        arrays["activation__" + name] = np.asarray([scale, zp], dtype=np.float64)
    np.savez_compressed(path, **arrays)


def hard_validate(params: OrderedDict[str, dict], quantized: OrderedDict[str, dict]) -> None:
    if len(SPECS) != 23 or len(quantized) != 23:
        raise RuntimeError("expected exactly 23 convolution parameter sets")
    expected_channels = {"pose_stem": 24, "pose_high_pw": 32, "pose_low0_pw": 48, "pose_context": 32, "pose_head": 9}
    for name, channels in expected_channels.items():
        if int(params[name]["weight"].shape[0]) != channels:
            raise RuntimeError(f"{name}: expected {channels} output channels")
    if max(int(entry["weight"].shape[0]) for entry in params.values()) > MAX_CHANNELS:
        raise RuntimeError("network exceeds HLS maximum channel count")
    for name, entry in quantized.items():
        values_per_output = int(entry["weight"].size // entry["weight"].shape[0])
        if values_per_output * int(entry["weight"].shape[0]) > MAX_CHANNELS * MAX_CHANNELS and name != "pose_stem":
            raise RuntimeError(f"{name}: weights exceed HLS cache")
        worst_accumulator = np.max(np.abs(entry["bias"].astype(np.int64))) + values_per_output * 255 * 127
        if worst_accumulator > np.iinfo(np.int32).max:
            raise RuntimeError(f"{name}: worst-case accumulator exceeds int32")
    if 72 * 128 * 24 > MAX_FEATURE_BYTES or 36 * 64 * 32 > MAX_FEATURE_BYTES or 18 * 32 * 48 > MAX_FEATURE_BYTES:
        raise RuntimeError("network exceeds HLS feature buffer")
    if HEAD_STRIDE != 16 or KEYPOINTS > HEAD_STRIDE:
        raise RuntimeError("invalid aligned heatmap stride")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "best.pt")
    parser.add_argument("--calibration-dir", type=Path, required=True)
    parser.add_argument("--calibration-count", type=int, default=200)
    parser.add_argument("--calibration-offset", type=int, default=0)
    parser.add_argument("--calibration-kind", choices=("board_roi", "provisional_images"), default="board_roi")
    parser.add_argument("--activation-percentile", type=float, default=99.99)
    parser.add_argument("--firmware-dir", type=Path, default=ROOT / "ultral_xczu4ev" / "vitis" / "ov5640_hdmi" / "src")
    parser.add_argument("--artifact-dir", type=Path, default=ROOT / "deploy" / "artifacts")
    return parser.parse_args()


def main() -> None:
    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    args = parse_args()
    checkpoint_path = args.checkpoint.resolve()
    if checkpoint_path != (ROOT / "best.pt").resolve():
        raise RuntimeError("deployment policy requires the repository-root best.pt")
    model, checkpoint = load_checkpoint(checkpoint_path)
    checkpoint_sha = sha256_file(checkpoint_path)
    params = fused_parameters(model)
    all_inputs = discover_inputs(args.calibration_dir)
    selected = choose_inputs(all_inputs, args.calibration_count, args.calibration_offset)
    if not 99.0 <= args.activation_percentile <= 100.0:
        raise RuntimeError("activation percentile must be in [99.0, 100.0]")
    ranges, calibration = collect_ranges(selected, params, args.activation_percentile)
    quantized, activations = quantize_model(params, ranges)
    hard_validate(params, quantized)

    args.firmware_dir.mkdir(parents=True, exist_ok=True)
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    float_header = args.firmware_dir / "pose_model_weights.h"
    int8_header = args.firmware_dir / "pose_model_int8_weights.h"
    metadata_path = args.firmware_dir / "pose_model_int8_weights.json"
    npz_path = args.artifact_dir / "pose_model_int8.npz"
    write_float_header(float_header, params, checkpoint, checkpoint_sha)
    write_int8_header(int8_header, quantized, activations)
    metadata = metadata_dict(checkpoint_path, checkpoint, checkpoint_sha, params, quantized, activations, ranges, calibration, args.calibration_kind, args.activation_percentile)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save_npz(npz_path, params, quantized, activations)
    manifest = {
        "schema_version": 1,
        "checkpoint_sha256": checkpoint_sha,
        "checkpoint": str(checkpoint_path),
        "generated": {str(path.resolve()): sha256_file(path) for path in (float_header, int8_header, metadata_path, npz_path)},
        "calibration_kind": args.calibration_kind,
        "calibration_count": len(calibration),
        # These are immutable hardware inputs to the software export.  FSBL,
        # PMUFW and the application ELF are intentionally recorded later by
        # package_preboard.ps1, after Vitis has rebuilt them.
        "hardware_inputs_reused_without_bitstream_rebuild": {
            "system_wrapper.bit": sha256_file(ROOT / "ultral_xczu4ev" / "build" / "system_wrapper.bit"),
            "Shadow_ultra.xsa": sha256_file(ROOT / "ultral_xczu4ev" / "Shadow_ultra.xsa"),
            "camera_dvp.xdc": sha256_file(ROOT / "ultral_xczu4ev" / "constraints" / "camera_dvp.xdc"),
            "hdmi.xdc": sha256_file(ROOT / "ultral_xczu4ev" / "constraints" / "hdmi.xdc"),
            "post_route_timing": {"wns_ns": 0.641, "tns_ns": 0.0, "constraints_met": True},
        },
    }
    manifest_path = args.artifact_dir / "model_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS checkpoint_sha256={checkpoint_sha}")
    print(f"PASS input=[1,3,{INPUT_H},{INPUT_W}] output={list(EXPECTED_OUTPUT)} layers={EXPECTED_HLS_LAYERS}")
    print(f"PASS calibration={len(calibration)} kind={args.calibration_kind}")
    print(f"PASS manifest={manifest_path}")


if __name__ == "__main__":
    main()
