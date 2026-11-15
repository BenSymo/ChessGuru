// Rebuild the PDFs in docs/ from the HTML files in this folder.
// Needs Node.js and Playwright (npm install playwright && npx playwright install chromium).
// Run from the repository root: node docs/pdf-source/build.js
const path = require("path");
const { chromium } = require("playwright");

const DOCS = ["data_lineage", "data_dictionary"];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  for (const name of DOCS) {
    const source = path.join(__dirname, `${name}.html`);
    const target = path.join(__dirname, "..", `${name}.pdf`);
    await page.goto(`file://${source}`);
    await page.pdf({ path: target, preferCSSPageSize: true, printBackground: true });
    console.log(`Wrote ${path.relative(process.cwd(), target)}`);
  }
  await browser.close();
})();
