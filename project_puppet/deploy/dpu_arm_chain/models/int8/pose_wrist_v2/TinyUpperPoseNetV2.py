# GENETARED BY NNDCT, DO NOT EDIT!

import torch
from torch import tensor
import pytorch_nndct as py_nndct

class TinyUpperPoseNetV2(py_nndct.nn.NndctQuantModel):
    def __init__(self):
        super(TinyUpperPoseNetV2, self).__init__()
        self.module_0 = py_nndct.nn.Input() #TinyUpperPoseNetV2::input_0
        self.module_1 = py_nndct.nn.Conv2d(in_channels=3, out_channels=24, kernel_size=[3, 3], stride=[2, 2], padding=[1, 1], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/ConvBnRelu[stem]/Conv2d[0]/input.3
        self.module_2 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/ConvBnRelu[stem]/ReLU[2]/input.7
        self.module_3 = py_nndct.nn.Conv2d(in_channels=24, out_channels=24, kernel_size=[3, 3], stride=[2, 2], padding=[1, 1], dilation=[1, 1], groups=24, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/DepthwiseSeparable[high]/Sequential[depthwise]/Conv2d[0]/input.9
        self.module_4 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/DepthwiseSeparable[high]/Sequential[depthwise]/ReLU[2]/input.13
        self.module_5 = py_nndct.nn.Conv2d(in_channels=24, out_channels=32, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/DepthwiseSeparable[high]/Sequential[pointwise]/Conv2d[0]/input.15
        self.module_6 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/DepthwiseSeparable[high]/Sequential[pointwise]/ReLU[2]/input.19
        self.module_7 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[3, 3], stride=[1, 1], padding=[1, 1], dilation=[1, 1], groups=32, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[0]/Sequential[depthwise]/Conv2d[0]/input.21
        self.module_8 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[0]/Sequential[depthwise]/ReLU[2]/input.25
        self.module_9 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[0]/Sequential[pointwise]/Conv2d[0]/input.27
        self.module_10 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[0]/Sequential[pointwise]/ReLU[2]/3434
        self.module_11 = py_nndct.nn.Add() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[0]/input.31
        self.module_12 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[3, 3], stride=[1, 1], padding=[1, 1], dilation=[1, 1], groups=32, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[1]/Sequential[depthwise]/Conv2d[0]/input.33
        self.module_13 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[1]/Sequential[depthwise]/ReLU[2]/input.37
        self.module_14 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[1]/Sequential[pointwise]/Conv2d[0]/input.39
        self.module_15 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[1]/Sequential[pointwise]/ReLU[2]/3488
        self.module_16 = py_nndct.nn.Add() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[high_refine]/DepthwiseSeparable[1]/input.43
        self.module_17 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[3, 3], stride=[2, 2], padding=[1, 1], dilation=[1, 1], groups=32, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[0]/Sequential[depthwise]/Conv2d[0]/input.45
        self.module_18 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[0]/Sequential[depthwise]/ReLU[2]/input.49
        self.module_19 = py_nndct.nn.Conv2d(in_channels=32, out_channels=48, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[0]/Sequential[pointwise]/Conv2d[0]/input.51
        self.module_20 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[0]/Sequential[pointwise]/ReLU[2]/input.55
        self.module_21 = py_nndct.nn.Conv2d(in_channels=48, out_channels=48, kernel_size=[3, 3], stride=[1, 1], padding=[1, 1], dilation=[1, 1], groups=48, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[1]/Sequential[depthwise]/Conv2d[0]/input.57
        self.module_22 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[1]/Sequential[depthwise]/ReLU[2]/input.61
        self.module_23 = py_nndct.nn.Conv2d(in_channels=48, out_channels=48, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[1]/Sequential[pointwise]/Conv2d[0]/input.63
        self.module_24 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[1]/Sequential[pointwise]/ReLU[2]/3594
        self.module_25 = py_nndct.nn.Add() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[1]/input.67
        self.module_26 = py_nndct.nn.Conv2d(in_channels=48, out_channels=48, kernel_size=[3, 3], stride=[1, 1], padding=[1, 1], dilation=[1, 1], groups=48, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[2]/Sequential[depthwise]/Conv2d[0]/input.69
        self.module_27 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[2]/Sequential[depthwise]/ReLU[2]/input.73
        self.module_28 = py_nndct.nn.Conv2d(in_channels=48, out_channels=48, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[2]/Sequential[pointwise]/Conv2d[0]/input.75
        self.module_29 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[2]/Sequential[pointwise]/ReLU[2]/3648
        self.module_30 = py_nndct.nn.Add() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[2]/input.79
        self.module_31 = py_nndct.nn.Conv2d(in_channels=48, out_channels=48, kernel_size=[3, 3], stride=[1, 1], padding=[1, 1], dilation=[1, 1], groups=48, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[3]/Sequential[depthwise]/Conv2d[0]/input.81
        self.module_32 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[3]/Sequential[depthwise]/ReLU[2]/input.85
        self.module_33 = py_nndct.nn.Conv2d(in_channels=48, out_channels=48, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[3]/Sequential[pointwise]/Conv2d[0]/input.87
        self.module_34 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[3]/Sequential[pointwise]/ReLU[2]/3702
        self.module_35 = py_nndct.nn.Add() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[low]/DepthwiseSeparable[3]/input.91
        self.module_36 = py_nndct.nn.Conv2d(in_channels=48, out_channels=32, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[context_projection]/Conv2d[0]/input.93
        self.module_37 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[context_projection]/ReLU[2]/context
        self.module_38 = py_nndct.nn.Interpolate() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/3735
        self.module_39 = py_nndct.nn.Add() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/input.97
        self.module_40 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[3, 3], stride=[1, 1], padding=[1, 1], dilation=[1, 1], groups=32, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[0]/Sequential[depthwise]/Conv2d[0]/input.99
        self.module_41 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[0]/Sequential[depthwise]/ReLU[2]/input.103
        self.module_42 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[0]/Sequential[pointwise]/Conv2d[0]/input.105
        self.module_43 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[0]/Sequential[pointwise]/ReLU[2]/3789
        self.module_44 = py_nndct.nn.Add() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[0]/input.109
        self.module_45 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[3, 3], stride=[1, 1], padding=[1, 1], dilation=[1, 1], groups=32, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[1]/Sequential[depthwise]/Conv2d[0]/input.111
        self.module_46 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[1]/Sequential[depthwise]/ReLU[2]/input.115
        self.module_47 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[1]/Sequential[pointwise]/Conv2d[0]/input.117
        self.module_48 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[1]/Sequential[pointwise]/ReLU[2]/3843
        self.module_49 = py_nndct.nn.Add() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[1]/input.121
        self.module_50 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[3, 3], stride=[1, 1], padding=[1, 1], dilation=[1, 1], groups=32, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[2]/Sequential[depthwise]/Conv2d[0]/input.123
        self.module_51 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[2]/Sequential[depthwise]/ReLU[2]/input.127
        self.module_52 = py_nndct.nn.Conv2d(in_channels=32, out_channels=32, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[2]/Sequential[pointwise]/Conv2d[0]/input.129
        self.module_53 = py_nndct.nn.ReLU(inplace=False) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[2]/Sequential[pointwise]/ReLU[2]/3897
        self.module_54 = py_nndct.nn.Add() #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Sequential[refine]/DepthwiseSeparable[2]/input
        self.module_55 = py_nndct.nn.Conv2d(in_channels=32, out_channels=9, kernel_size=[1, 1], stride=[1, 1], padding=[0, 0], dilation=[1, 1], groups=1, bias=True) #TinyUpperPoseNetV2::TinyUpperPoseNetV2/Conv2d[head]/3918

    @py_nndct.nn.forward_processor
    def forward(self, *args):
        output_module_0 = self.module_0(input=args[0])
        output_module_0 = self.module_1(output_module_0)
        output_module_0 = self.module_2(output_module_0)
        output_module_0 = self.module_3(output_module_0)
        output_module_0 = self.module_4(output_module_0)
        output_module_0 = self.module_5(output_module_0)
        output_module_0 = self.module_6(output_module_0)
        output_module_7 = self.module_7(output_module_0)
        output_module_7 = self.module_8(output_module_7)
        output_module_7 = self.module_9(output_module_7)
        output_module_7 = self.module_10(output_module_7)
        output_module_7 = self.module_11(input=output_module_7, other=output_module_0, alpha=1)
        output_module_12 = self.module_12(output_module_7)
        output_module_12 = self.module_13(output_module_12)
        output_module_12 = self.module_14(output_module_12)
        output_module_12 = self.module_15(output_module_12)
        output_module_12 = self.module_16(input=output_module_12, other=output_module_7, alpha=1)
        output_module_17 = self.module_17(output_module_12)
        output_module_17 = self.module_18(output_module_17)
        output_module_17 = self.module_19(output_module_17)
        output_module_17 = self.module_20(output_module_17)
        output_module_21 = self.module_21(output_module_17)
        output_module_21 = self.module_22(output_module_21)
        output_module_21 = self.module_23(output_module_21)
        output_module_21 = self.module_24(output_module_21)
        output_module_21 = self.module_25(input=output_module_21, other=output_module_17, alpha=1)
        output_module_26 = self.module_26(output_module_21)
        output_module_26 = self.module_27(output_module_26)
        output_module_26 = self.module_28(output_module_26)
        output_module_26 = self.module_29(output_module_26)
        output_module_26 = self.module_30(input=output_module_26, other=output_module_21, alpha=1)
        output_module_31 = self.module_31(output_module_26)
        output_module_31 = self.module_32(output_module_31)
        output_module_31 = self.module_33(output_module_31)
        output_module_31 = self.module_34(output_module_31)
        output_module_31 = self.module_35(input=output_module_31, other=output_module_26, alpha=1)
        output_module_31 = self.module_36(output_module_31)
        output_module_31 = self.module_37(output_module_31)
        output_module_31 = self.module_38(input=output_module_31, size=None, scale_factor=[2.0,2.0], mode='nearest')
        output_module_39 = self.module_39(input=output_module_12, other=output_module_31, alpha=1)
        output_module_40 = self.module_40(output_module_39)
        output_module_40 = self.module_41(output_module_40)
        output_module_40 = self.module_42(output_module_40)
        output_module_40 = self.module_43(output_module_40)
        output_module_40 = self.module_44(input=output_module_40, other=output_module_39, alpha=1)
        output_module_45 = self.module_45(output_module_40)
        output_module_45 = self.module_46(output_module_45)
        output_module_45 = self.module_47(output_module_45)
        output_module_45 = self.module_48(output_module_45)
        output_module_45 = self.module_49(input=output_module_45, other=output_module_40, alpha=1)
        output_module_50 = self.module_50(output_module_45)
        output_module_50 = self.module_51(output_module_50)
        output_module_50 = self.module_52(output_module_50)
        output_module_50 = self.module_53(output_module_50)
        output_module_50 = self.module_54(input=output_module_50, other=output_module_45, alpha=1)
        output_module_50 = self.module_55(output_module_50)
        return output_module_50
