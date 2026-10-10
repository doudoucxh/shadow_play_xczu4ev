<AutoPilot:project xmlns:AutoPilot="com.autoesl.autopilot.project" projectType="C/C++" top="pose_cnn_accel" name="model_csim_build">
    <includePaths/>
    <libraryFlag/>
    <files>
        <file name="D:/Desktop/project_puppet/ultral_xczu4ev/hls/pose_cnn_accel/tb_pose_model.cpp" sc="0" tb="1" cflags=" -Wno-unknown-pragmas" csimflags=" -Wno-unknown-pragmas" blackbox="false"/>
        <file name="D:/Desktop/project_puppet/ultral_xczu4ev/hls/pose_cnn_accel/pose_cnn_accel.h" sc="0" tb="false" cflags="" csimflags="" blackbox="false"/>
        <file name="D:/Desktop/project_puppet/ultral_xczu4ev/hls/pose_cnn_accel/pose_cnn_accel.cpp" sc="0" tb="false" cflags="" csimflags="" blackbox="false"/>
    </files>
    <solutions>
        <solution name="solution1" status=""/>
    </solutions>
    <Simulation argv="D:/Desktop/project_puppet/deploy/csim/input_bgr.bin D:/Desktop/project_puppet/deploy/csim/hls_heatmap.bin">
        <SimFlow name="csim" setup="false" optimizeCompile="false" clean="true" ldflags="" mflags=""/>
    </Simulation>
</AutoPilot:project>

