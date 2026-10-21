/** @type {import('next').NextConfig} */
const nextConfig = {
    output: "standalone",
    eslint: { ignoreDuringBuilds: true },
    typescript: { ignoreBuildErrors: true },
    // the browser calls /hub on this server, which forwards to the API; the API stays bound to this PC only
    async rewrites() {
        const api = process.env.HUB_API_ORIGIN ?? "http://127.0.0.1:8000";
        return [{ source: "/hub/:path*", destination: `${api}/hub/:path*` }];
    },
};

export default nextConfig;
