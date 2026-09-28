/** @type {import('next').NextConfig} */
const isGithubPages = process.env.GITHUB_ACTIONS === "true";

module.exports = {
  output: "export",
  // Cloudflare Workers Static Assets can serve generated *.html routes
  // directly as /live, /analysis, etc. Keep canonical routes slashless.
  trailingSlash: false,
  basePath: isGithubPages ? "/Tembo-forex-bot" : "",
  images: { unoptimized: true },
};
