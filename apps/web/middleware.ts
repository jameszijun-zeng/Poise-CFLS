export { default } from "next-auth/middleware";

export const config = {
  matcher: [
    "/chat/:path*",
    "/forecast/:path*",
    "/plans/:path*",
    "/alerts/:path*",
    "/data/:path*",
    "/admin/:path*",
    "/accuracy/:path*",
    "/dashboard/:path*",
  ],
};
