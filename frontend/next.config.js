/** @type {import('next').NextConfig} */
const isGithubPages = process.env.GITHUB_ACTIONS === "true";

module.exports = {
  output: "export",
  trailingSlash: true,
  basePath: isGithubPages ? "/Tembo-forex-bot" : "",
  images: { unoptimized: true },
};
