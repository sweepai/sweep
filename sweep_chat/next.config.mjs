/** @type {import('next').NextConfig} */
const nextConfig = {};

export default {
    async rewrites() {
        return [
            {
                source: '/api/:path*',
                destination: `${process.env.BACKEND_URL}/chat/:path*`, // FastAPI server
            },
        ]
    },
    ...nextConfig,
};
