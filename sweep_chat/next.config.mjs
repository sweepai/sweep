/** @type {import('next').NextConfig} */
const nextConfig = {};

export default {
    async rewrites() {
        return [
            {
                source: '/backend/:path*',
                destination: `${process.env.BACKEND_URL}/chat/:path*`, // FastAPI server
            },
        ]
    },
    ...nextConfig,
};
