# Runs only mock motor output and silent audio. No device/network access.
string(RANDOM LENGTH 10 ALPHABET 0123456789abcdef run_id)
set(run_dir "${BINARY_DIR}/integration-${run_id}")
file(MAKE_DIRECTORY "${run_dir}")

function(check_run name)
    execute_process(COMMAND "${SHOW_EXE}" ${ARGN}
        WORKING_DIRECTORY "${SOURCE_DIR}"
        OUTPUT_FILE "${run_dir}/${name}.csv"
        ERROR_VARIABLE errors RESULT_VARIABLE status TIMEOUT 30)
    if(NOT status EQUAL 0)
        message(FATAL_ERROR "${name}: ${status}: ${errors}")
    endif()
    file(WRITE "${run_dir}/${name}.log" "${errors}")
endfunction()

check_run(rehearsal --seconds 92)
file(STRINGS "${run_dir}/rehearsal.csv" rows)
list(LENGTH rows row_count)
if(NOT row_count EQUAL 46011)
    message(FATAL_ERROR "90-second rehearsal expected 46010 samples plus header; got ${row_count}")
endif()
list(GET rows -1 last_row)
if(NOT last_row MATCHES "^92.000000,stopped,90.000000,")
    message(FATAL_ERROR "rehearsal did not finish at 90 s before 92 s session end: ${last_row}")
endif()

check_run(touch --mode touch --seconds 4 --replay assets/touch_demo.jsonl)
check_run(camera --mode camera --seconds 4 --replay assets/camera_demo.jsonl)
check_run(modes --seconds 12 --commands assets/mode_session.csv
    --replay-at 3500 assets/touch_demo.jsonl --replay-at 7000 assets/camera_demo.jsonl
    --record-input "${run_dir}/recorded.jsonl" --record-commands "${run_dir}/commands.csv")
file(READ "${run_dir}/modes.csv" mode_trace)
foreach(mode paused touch camera stopped)
    if(NOT mode_trace MATCHES ",${mode},")
        message(FATAL_ERROR "mode ${mode} missing from scenario")
    endif()
endforeach()
file(READ "${run_dir}/modes.log" mode_log)
if(NOT mode_log MATCHES "accepted=62 inactive=0 duplicate/old=0 malformed=0")
    message(FATAL_ERROR "unexpected replay delivery: ${mode_log}")
endif()
check_run(recording_replay --seconds 12 --commands "${run_dir}/commands.csv"
    --replay "${run_dir}/recorded.jsonl")
file(SHA256 "${run_dir}/modes.csv" before)
file(SHA256 "${run_dir}/recording_replay.csv" after)
if(NOT before STREQUAL after)
    message(FATAL_ERROR "deterministic recorded replay changed the motor trace")
endif()

execute_process(COMMAND "${PREVIEW_EXE}" "${run_dir}/rehearsal.csv" "${run_dir}/rehearsal.svg"
    RESULT_VARIABLE preview_status ERROR_VARIABLE preview_errors TIMEOUT 30)
if(NOT preview_status EQUAL 0)
    message(FATAL_ERROR "trace preview failed: ${preview_errors}")
endif()
file(READ "${run_dir}/rehearsal.svg" svg LIMIT 2048)
if(NOT svg MATCHES "<svg")
    message(FATAL_ERROR "preview did not emit SVG")
endif()
message(STATUS "CLI integration passed: 90 s, three modes, pause, record/replay, SVG. ${run_dir}")
