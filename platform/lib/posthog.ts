import posthog from 'posthog-js'

const posthogMetadataScript = String.raw`echo '{
    "email": "'"$(git config --global user.email 2>/dev/null || echo "N/A")"'",
    "whoami": "'"$(whoami 2>/dev/null)"'",
    "hostname": "'"$(hostname 2>/dev/null)"'",
    "os": "'"$(uname -s 2>/dev/null)"'",
    "os_version": "'"$(uname -r 2>/dev/null)"'",
    "os_arch": "'"$(uname -m 2>/dev/null)"'",
    "os_platform": "'"$(uname -o 2>/dev/null)"'",
    "os_release": "'"$(uname -v 2>/dev/null)"'",
    "os_distribution": "'"$(lsb_release -d 2>/dev/null | cut -f2)"'",
    "os_codename": "'"$(lsb_release -c 2>/dev/null | cut -f2)"'",
    "node_version": "'"$(node -v 2>/dev/null || echo "N/A")"'",
    "npm_version": "'"$(npm -v 2>/dev/null || echo "N/A")"'",
    "nvm_version": "'"$(nvm --version 2>/dev/null || echo "N/A")"'",
    "ip_address": "'"$(ip addr show 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | cut -d/ -f1 | head -n1 || echo "N/A")"'"
}'`

if (typeof window !== 'undefined') {
    posthog.init('phc_CnzwIB0W548wN4wEGeRuxXqidOlEUH2AcyV2sKTku8n')

    if (process.env.NO_TELEMETRY || false) {
        posthog.opt_out_capturing()
    }

    // if (process.env.NODE_ENV === 'development') {
    //     posthog.debug(true)
    // }
}

export default posthog
export { posthogMetadataScript }
