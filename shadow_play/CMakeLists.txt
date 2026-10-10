cmake_minimum_required(VERSION 3.16)
project(shadow_play VERSION 0.3.0 LANGUAGES CXX)

set(CMAKE_CXX_EXTENSIONS OFF)
option(SHADOW_ENABLE_ALSA "Enable real PCM16 WAV playback when ALSA is available" ON)
option(SHADOW_REQUIRE_ALSA "Fail configuration if real audio backend cannot be built" OFF)
option(SHADOW_BUILD_CAPTURE "Build the desktop calibration capture interface" OFF)

add_library(shadow_mapping
    src/motion_mapper.cpp
    src/calibration_csv.cpp
)
target_include_directories(shadow_mapping PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
target_compile_features(shadow_mapping PUBLIC cxx_std_17)
set_target_properties(shadow_mapping PROPERTIES CXX_EXTENSIONS OFF)

add_executable(mapper_demo src/demo.cpp)
target_link_libraries(mapper_demo PRIVATE shadow_mapping)

add_library(shadow_runtime
    src/script.cpp
    src/audio.cpp
    src/input.cpp
    src/controller.cpp
    src/motor_backend.cpp
    src/runtime_io.cpp
    src/udp.cpp
)
target_link_libraries(shadow_runtime PUBLIC shadow_mapping)
target_include_directories(shadow_runtime SYSTEM PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/third_party)
target_compile_features(shadow_runtime PUBLIC cxx_std_17)

find_package(Threads REQUIRED)
target_link_libraries(shadow_runtime PUBLIC Threads::Threads)
if(WIN32)
    target_link_libraries(shadow_runtime PRIVATE ws2_32)
endif()
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
    target_link_libraries(shadow_runtime PUBLIC stdc++fs)
endif()
if(SHADOW_ENABLE_ALSA AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
    find_package(ALSA QUIET)
    if(ALSA_FOUND)
        target_compile_definitions(shadow_runtime PRIVATE SHADOW_HAVE_ALSA=1)
        target_include_directories(shadow_runtime PRIVATE ${ALSA_INCLUDE_DIRS})
        target_link_libraries(shadow_runtime PRIVATE ${ALSA_LIBRARIES})
        message(STATUS "Real WAV playback: ALSA enabled")
    endif()
endif()
if(NOT ALSA_FOUND)
    if(SHADOW_REQUIRE_ALSA)
        message(FATAL_ERROR "ALSA playback required but unavailable. Install libasound2-dev / target SDK audio libs.")
    endif()
    message(STATUS "Real WAV playback: unavailable; silent simulation clock still works")
endif()

add_executable(shadow_show src/show_main.cpp)
target_link_libraries(shadow_show PRIVATE shadow_runtime)
add_executable(shadow_send src/input_sender.cpp)
target_link_libraries(shadow_send PRIVATE shadow_runtime)
add_executable(trace_preview src/trace_preview.cpp)
target_compile_features(trace_preview PRIVATE cxx_std_17)
add_executable(make_cue_wav src/make_cue_wav.cpp)
target_compile_features(make_cue_wav PRIVATE cxx_std_17)

include(CTest)
if(BUILD_TESTING)
    add_executable(mapper_tests tests/mapper_tests.cpp)
    target_link_libraries(mapper_tests PRIVATE shadow_mapping)
    add_test(NAME mapping_behaviour COMMAND mapper_tests)
    foreach(suite script_audio input controller motor_protocol)
        add_executable(${suite}_tests tests/${suite}_tests.cpp)
        target_link_libraries(${suite}_tests PRIVATE shadow_runtime)
        target_include_directories(${suite}_tests SYSTEM PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/third_party)
        if(ALSA_FOUND AND SHADOW_ENABLE_ALSA)
            target_compile_definitions(${suite}_tests PRIVATE SHADOW_HAVE_ALSA=1)
        endif()
        add_test(NAME ${suite}_behaviour COMMAND ${suite}_tests)
    endforeach()
    if(NOT CMAKE_CROSSCOMPILING)
        find_package(Python3 COMPONENTS Interpreter QUIET)
        if(Python3_Interpreter_FOUND)
            add_test(NAME follow_sender_behaviour COMMAND ${Python3_EXECUTABLE}
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_follow_sender.py)
            add_test(NAME csv_trace_validation COMMAND ${Python3_EXECUTABLE}
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_csv_summary.py)
            add_test(NAME follow_to_motor_chain COMMAND ${Python3_EXECUTABLE}
                ${CMAKE_CURRENT_SOURCE_DIR}/tests/follow_chain_test.py
                $<TARGET_FILE:shadow_show> ${CMAKE_CURRENT_SOURCE_DIR})
            set_tests_properties(follow_sender_behaviour follow_to_motor_chain PROPERTIES TIMEOUT 20)
        endif()
    endif()
    add_test(NAME cli_integration COMMAND ${CMAKE_COMMAND}
        -DSHOW_EXE=$<TARGET_FILE:shadow_show>
        -DPREVIEW_EXE=$<TARGET_FILE:trace_preview>
        -DSOURCE_DIR=${CMAKE_CURRENT_SOURCE_DIR}
        -DBINARY_DIR=${CMAKE_CURRENT_BINARY_DIR}
        -P ${CMAKE_CURRENT_SOURCE_DIR}/tests/cli_integration.cmake)
    # Cross builds also need this executable for tests run on the target board.
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        add_executable(live_udp_tests tests/live_udp_tests.cpp)
        target_link_libraries(live_udp_tests PRIVATE shadow_runtime)
        add_test(NAME live_udp_integration COMMAND live_udp_tests
            $<TARGET_FILE:shadow_show> ${CMAKE_CURRENT_SOURCE_DIR})
        set_tests_properties(live_udp_integration PROPERTIES TIMEOUT 15)
    endif()
endif()

set(shadow_targets shadow_mapping shadow_runtime mapper_demo shadow_show shadow_send trace_preview make_cue_wav)
if(SHADOW_BUILD_CAPTURE)
    find_package(Qt5 5.12 REQUIRED COMPONENTS Widgets Network)
    find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs videoio)
    add_library(shadow_capture_session src/capture_session.cpp)
    target_include_directories(shadow_capture_session PUBLIC include PRIVATE third_party)
    target_compile_features(shadow_capture_session PUBLIC cxx_std_17)
    add_library(shadow_capture_geometry src/capture_geometry.cpp)
    target_include_directories(shadow_capture_geometry PUBLIC include ${OpenCV_INCLUDE_DIRS})
    target_compile_features(shadow_capture_geometry PUBLIC cxx_std_17)
    target_link_libraries(shadow_capture_geometry PUBLIC ${OpenCV_LIBS})
    add_executable(shadow_capture src/capture_main.cpp)
    target_include_directories(shadow_capture PRIVATE third_party)
    target_link_libraries(shadow_capture PRIVATE shadow_capture_session shadow_capture_geometry Qt5::Widgets Qt5::Network Threads::Threads)
    list(APPEND shadow_targets shadow_capture_session shadow_capture_geometry shadow_capture)
    if(BUILD_TESTING)
        add_executable(capture_session_tests tests/capture_session_tests.cpp)
        target_include_directories(capture_session_tests PRIVATE third_party)
        target_link_libraries(capture_session_tests PRIVATE shadow_capture_session)
        add_executable(capture_geometry_tests tests/capture_geometry_tests.cpp)
        target_link_libraries(capture_geometry_tests PRIVATE shadow_capture_geometry)
        add_executable(capture_http_tests tests/capture_http_tests.cpp)
        target_link_libraries(capture_http_tests PRIVATE shadow_capture_geometry Qt5::Network)
        add_test(NAME capture_http_freshness COMMAND capture_http_tests)
        set_tests_properties(capture_http_freshness PROPERTIES TIMEOUT 15)
        list(APPEND shadow_targets capture_session_tests capture_geometry_tests)
        add_test(NAME capture_session COMMAND capture_session_tests ${CMAKE_CURRENT_SOURCE_DIR}/config/capture.demo.json)
        add_test(NAME capture_geometry COMMAND capture_geometry_tests)
        file(MAKE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/capture-smoke)
        foreach(mode demo manual front)
            set(capture_args --demo --config ${CMAKE_CURRENT_SOURCE_DIR}/config/capture.demo.json
                --session ${CMAKE_CURRENT_BINARY_DIR}/capture-smoke/${mode}
                --smoke-test ${CMAKE_CURRENT_BINARY_DIR}/capture-smoke/${mode}.png)
            if(mode STREQUAL "manual")
                list(APPEND capture_args --backend manual_unconfirmed)
            elseif(mode STREQUAL "front")
                list(APPEND capture_args --reference-view front)
            endif()
            add_test(NAME capture_gui_${mode} COMMAND shadow_capture ${capture_args})
            set_tests_properties(capture_gui_${mode} PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen" TIMEOUT 20)
        endforeach()
        if(Python3_Interpreter_FOUND AND NOT CMAKE_CROSSCOMPILING)
            add_test(NAME servo_commissioning COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_servo_commissioning.py)
            set_tests_properties(servo_commissioning PROPERTIES TIMEOUT 15)
            foreach(suite bridge handoff)
                add_test(NAME capture_${suite} COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_capture_${suite}.py)
                set_tests_properties(capture_${suite} PROPERTIES TIMEOUT 30)
            endforeach()
        endif()
    endif()
    install(TARGETS shadow_capture RUNTIME DESTINATION bin)
endif()
if(BUILD_TESTING)
    list(APPEND shadow_targets mapper_tests script_audio_tests input_tests controller_tests motor_protocol_tests)
    if(TARGET live_udp_tests)
        list(APPEND shadow_targets live_udp_tests)
    endif()
endif()
foreach(target ${shadow_targets})
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /utf-8)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endforeach()

# Both export backends are software-only; board drivers are supplied by the team.
install(TARGETS shadow_show shadow_send trace_preview make_cue_wav RUNTIME DESTINATION bin)
install(DIRECTORY assets config DESTINATION share/shadow-play
    FILES_MATCHING PATTERN "*.json" PATTERN "*.jsonl" PATTERN "*.csv" PATTERN "*.wav")
install(FILES third_party/nlohmann/LICENSE.MIT DESTINATION share/shadow-play/licenses/nlohmann-json)
install(FILES README.md DESTINATION share/shadow-play)
install(DIRECTORY docs DESTINATION share/shadow-play FILES_MATCHING PATTERN "*.md")
install(DIRECTORY integrations DESTINATION share/shadow-play
    FILES_MATCHING PATTERN "*.py" PATTERN "*.md" PATTERN "__pycache__" EXCLUDE)
