/* Optional real-browser smoke test. Requires Microsoft Edge or Chrome on Windows. */
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const chromeCandidates = [
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
];
const chrome = chromeCandidates.find(fs.existsSync);
const portNumber = Number(process.env.FLOOD_TEST_PORT || 8001);
const origin = "http://127.0.0.1:" + portNumber;
if (!chrome) throw new Error("Install Edge or Chrome to run this browser check.");
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "flood-dashboard-"));
const child = spawn(chrome, [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  "--remote-allow-origins=*", "--remote-debugging-port=0", "--user-data-dir=" + profile,
  origin + "/",
], { stdio: "ignore", windowsHide: true });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function waitFor(fn, label, timeout = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (child.exitCode !== null) throw new Error("Browser exited early (" + child.exitCode + ")");
    const value = await fn();
    if (value) return value;
    await sleep(200);
  }
  throw new Error("Timed out waiting for " + label);
}
async function main() {
  const activeFile = path.join(profile, "DevToolsActivePort");
  await waitFor(() => fs.existsSync(activeFile), "Chrome DevTools startup");
  const port = Number(fs.readFileSync(activeFile, "utf8").split(/\r?\n/)[0]);
  const page = await waitFor(async () => {
    const response = await fetch("http://127.0.0.1:" + port + "/json/list");
    const targets = await response.json();
    return targets.find(target => target.type === "page" && target.url.includes("127.0.0.1:" + portNumber));
  }, "dashboard page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  let nextId = 1;
  const pending = new Map();
  ws.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const p = pending.get(message.id); pending.delete(message.id);
      message.error ? p.reject(new Error(message.error.message)) : p.resolve(message.result);
    }
  });
  function send(method, params = {}) {
    const id = nextId++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(expression) {
    const result = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  }
  try {
    await send("Runtime.enable");
    const init = await waitFor(async () => {
      const status = await evaluate("document.querySelector('#service-status')?.textContent || ''");
      return status.includes("india-location-demo-6") ? status : null;
    }, "updated dashboard initialization");
    const weatherReady = await waitFor(() => evaluate("document.querySelector('#weather-status')?.textContent.includes('updated from Open-Meteo')"), "live Guwahati weather forecast");
    const weatherCities = await evaluate("document.querySelectorAll('#weather-city option').length");
    if (weatherCities !== 11 || !weatherReady) throw new Error("Weather location selector or initial real forecast failed");
    const weatherResults = [];
    for (const id of ["guwahati", "chennai", "patna"]) {
      await evaluate("(()=>{const s=document.querySelector('#weather-city');s.value=" + JSON.stringify(id) + ";s.dispatchEvent(new Event('change'))})()");
      const cityName = id === "guwahati" ? "Guwahati, Assam" : id === "chennai" ? "Chennai, Tamil Nadu" : "Patna, Bihar";
      await waitFor(() => evaluate("document.querySelector('#weather-results .weather-risk-intro')?.textContent.startsWith(" + JSON.stringify(cityName) + ") && document.querySelector('#weather-results .weather-risk-grid')?.children.length===8"), "live " + cityName + " result");
      const snapshot = await evaluate("(()=>({location:document.querySelector('#weather-results .weather-risk-intro').textContent,temperature:document.querySelector('#weather-results .weather-stat .value').textContent,rainfall:document.querySelectorAll('#weather-results .weather-stat .value')[5].textContent,risk:document.querySelector('#weather-results .weather-risk-result h3').textContent,bars:document.querySelectorAll('#weather-hourly-chart .weather-hour').length,retrieval:document.querySelector('#weather-results .weather-source').textContent}))()");
      if (!snapshot.temperature || !snapshot.retrieval.includes("Open-Meteo") || snapshot.bars !== 24) throw new Error("Incomplete weather display for " + cityName);
      weatherResults.push(snapshot);
    }
    await evaluate("(()=>{const s=document.querySelector('#weather-city');s.value='manual';s.dispatchEvent(new Event('change'));document.querySelector('#weather-latitude').value='12.9716';document.querySelector('#weather-longitude').value='77.5946'})()");
    await evaluate("document.querySelector('#weather-fetch').click()");
    await waitFor(() => evaluate("document.querySelector('#weather-results .weather-risk-intro')?.textContent.startsWith('Manual coordinates')"), "manual coordinate weather result");
    await evaluate("document.querySelector('#weather-latitude').value='91';document.querySelector('#weather-fetch').click()");
    const manualValidation = await waitFor(() => evaluate("document.querySelector('#weather-status').textContent.includes('Latitude must be between')"), "manual weather coordinate validation");
    const globePixels = await evaluate("(()=>{const c=document.querySelector('#globe'),x=c.getContext('2d').getImageData(Math.floor(c.width/2),Math.floor(c.height/2),1,1).data;return c.width>0&&c.height>0&&x.some(v=>v>0)})()");
    if (!globePixels) throw new Error("The Earth globe canvas did not render");
    const zoomBefore = await evaluate("document.querySelector('#globe').toDataURL()");
    await evaluate("document.querySelector('#zoom-in').click()");
    const zoomAfter = await evaluate("document.querySelector('#globe').toDataURL()");
    if (zoomAfter === zoomBefore) throw new Error("Globe zoom control did not change the rendered image");
    await evaluate("document.querySelector('#globe').scrollIntoView({block:'center'})");
    const rect = JSON.parse(await evaluate("JSON.stringify((()=>{const r=document.querySelector('#globe').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})())"));
    const rotationBefore = await evaluate("document.querySelector('#globe').toDataURL()");
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x: rect.x, y: rect.y, button: "left", clickCount: 1 });
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: rect.x + 45, y: rect.y + 12, button: "left", buttons: 1 });
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: rect.x + 45, y: rect.y + 12, button: "left", clickCount: 1 });
    const rotationAfter = await evaluate("document.querySelector('#globe').toDataURL()");
    if (rotationAfter === rotationBefore) throw new Error("Globe drag did not rotate the rendered view");
    const clusterPoint = await evaluate("(()=>{const c=document.querySelector('#globe'),r=c.getBoundingClientRect();for(let y=.25;y<.76;y+=.01)for(let x=.25;x<.76;x+=.01){const px=r.left+r.width*x,py=r.top+r.height*y;c.dispatchEvent(new PointerEvent('pointermove',{clientX:px,clientY:py,bubbles:true}));if(c.title.includes('satellite scene centers overlap'))return{x:px,y:py,title:c.title}}return null})()");
    if (!clusterPoint || !clusterPoint.title.includes("68 satellite scene centers")) throw new Error("Overlapping scene marker did not expose cluster hover details: " + JSON.stringify(clusterPoint));
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x: clusterPoint.x, y: clusterPoint.y, button: "left", clickCount: 1 });
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: clusterPoint.x, y: clusterPoint.y, button: "left", clickCount: 1 });
    const clusterClick = await evaluate("document.querySelector('#map-caption').textContent");
    if (!clusterClick.includes("local satellite scene centers")) throw new Error("Clicking a detection cluster did not zoom/select the cluster");
    const locations = await waitFor(async () => {
      const count = await evaluate("document.querySelectorAll('#india-location option').length");
      return count > 1 ? count : null;
    }, "supported location options");
    if (locations < 2) throw new Error("Location selector only has " + locations + " options");
    const scenes = await (await fetch(origin + "/api/detections")).json();
    const firstScene = scenes.results[0];
    const markerStatus = await waitFor(() => evaluate("document.querySelector('#scene-marker-status')?.textContent || ''"), "marker inventory");
    if (scenes.valid_record_count !== 68 || scenes.invalid_record_count !== 0 || scenes.displayed_record_count !== 68 || !markerStatus.includes("68 valid records") || !markerStatus.includes("68 currently visible records")) throw new Error("Globe marker inventory did not expose all 68 valid records: " + markerStatus);
    await evaluate("document.querySelector('#scene-search').value=" + JSON.stringify(firstScene.scene_id) + ";document.querySelector('#scene-form').requestSubmit()");
    const sceneCoordinates = await evaluate("[document.querySelector('#latitude').value,document.querySelector('#longitude').value]");
    if (Math.abs(Number(sceneCoordinates[0]) - firstScene.center.latitude) > 0.00001 ||
        Math.abs(Number(sceneCoordinates[1]) - firstScene.center.longitude) > 0.00001) {
      throw new Error("Satellite scene selection did not move the location to its footprint center");
    }
    await evaluate("document.querySelector('#load-before-after').click()");
    const pair = await waitFor(() => evaluate("document.querySelector('#before-after-status').textContent.includes('Complete')"), "before/after render");
    const imageWidth = await evaluate("document.querySelector('#before-after-results img')?.naturalWidth || 0");
    if (!pair || imageWidth < 100) throw new Error("Before/after comparison image did not render");
    const pairText = await evaluate("document.querySelector('#before-after-results').innerText");
    if (!pairText.includes("S1A_IW_GRDH_1SDV_20160719T234621") || !pairText.includes("S1A_IW_GRDH_1SDV_20160812T234622") || !pairText.includes("did not segment any pixels above threshold")) throw new Error("Before/after scene provenance or empty-mask explanation is missing");
    await evaluate("document.querySelector('#demo-form').requestSubmit()");
    const gauge = await waitFor(() => evaluate("document.querySelector('#demo-result').textContent.includes('days old') && document.querySelector('#demo-result').textContent.includes('stale')"), "stale gauge display");
    if (!gauge) throw new Error("Expected stale Alipingal reading was not shown");
    const gaugeText = await evaluate("document.querySelector('#demo-result').innerText");
    if (!gaugeText.includes("10.85") || !gaugeText.includes("11.76") || !gaugeText.includes("13.11")) throw new Error("Gauge thresholds or historical high are missing");
    await evaluate("document.querySelector('#river-prediction-form').requestSubmit()");
    const forecast = await waitFor(() => evaluate("document.querySelector('#river-prediction-result').textContent.includes('Unavailable')"), "forecast unavailable state");
    const invalidCoords = await evaluate("fetch('/api/query?lat=92&lon=0').then(async r=>({status:r.status,body:await r.json()}))");
    if (invalidCoords.status !== 400 || !invalidCoords.body.error.toLowerCase().includes('latitude')) throw new Error('Out-of-range coordinates were not rejected');
    await evaluate("document.querySelector('#latitude').value=28.6139;document.querySelector('#longitude').value=77.209;document.querySelector('#coordinate-form').requestSubmit()");
    const discharge = await waitFor(() => evaluate("document.querySelector('#results').innerText.includes('24-hour forecast unavailable')"), "stale discharge unavailable message");
    await evaluate("document.querySelector('#india-location').value=document.querySelector('#india-location option:nth-child(2)').value;document.querySelector('#india-location').dispatchEvent(new Event('change'))");
    const coords = await evaluate("[document.querySelector('#latitude').value,document.querySelector('#longitude').value]");
    await send("DOM.enable");
    const documentRoot = await send("DOM.getDocument", { depth: -1 });
    const fileInput = await send("DOM.querySelector", {
      nodeId: documentRoot.root.nodeId, selector: "#satellite-image",
    });
    await send("DOM.setFileInputFiles", {
      nodeId: fileInput.nodeId,
      files: [path.resolve(__dirname, "..", "data", "S1GRDHand", "India_1017769_S1Hand.tif")],
    });
    await evaluate("document.querySelector('#process-image').click()");
    const uploadStatus = await waitFor(() => evaluate("document.querySelector('#satellite-status').textContent.startsWith('Complete')"), "browser upload segmentation", 60000);
    const uploadResult = await waitFor(() => evaluate("(()=>{const img=document.querySelector('#satellite-results img');return img&&img.naturalWidth>100?{text:document.querySelector('#satellite-results').innerText,imageWidth:img.naturalWidth,links:document.querySelectorAll('#satellite-results a').length}:null})()"), "uploaded overlay rendering", 20000);
    if (!uploadStatus || uploadResult.imageWidth < 100 || uploadResult.links < 3 || !uploadResult.text.includes("57.91%")) {
      throw new Error("Fresh satellite upload results were not rendered correctly");
    }
    console.log(JSON.stringify({
      status: "PASS", backend: init.trim(), supported_location_options: locations - 1, marker_inventory: markerStatus, discharge_unavailable_message: discharge, manual_coordinate_validation: invalidCoords,
      globe_canvas_rendered: globePixels, zoom_changed: zoomAfter !== zoomBefore,
      rotation_changed: rotationAfter !== rotationBefore,
      cluster_hover_and_click: clusterClick,
      live_weather_city_results: weatherResults,
      weather_manual_coordinate_validation: manualValidation,
      selected_scene: firstScene.scene_id,
      before_after_figure_width: imageWidth, gauge: "stale observation shown; no current category",
      before_after_provenance_and_empty_masks: true, gauge_thresholds_and_historical_high: true,
      future_forecast: "unavailable as required", selected_location_coordinates: coords,
      satellite_upload: "rendered 57.91% result with overlay and three downloads",
    }, null, 2));
  } finally {
    ws.close();
  }
}
main().catch(error => { console.error(error.stack || error); process.exitCode = 1; })
  .finally(() => { child.kill(); });
