set -e
systemctl stop shadow-uart-text-stream-20261020
if systemctl is-active --quiet shadow-uart-text-stream-20261020; then
    echo "ERROR: text stream is still active"
    exit 1
fi
echo "UART text stream stopped. No PWM or motor commands sent."
