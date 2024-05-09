/** @type {import('next').NextConfig} */
const nextConfig = {};

export default {
    async rewrites() {
        return [
            {
                source: '/backend/:path*',
                destination: `${process.env.BACKEND_URL}/chat/backend/:path*`, // FastAPI server
            },
        ]
    },
    ...nextConfig,
};
