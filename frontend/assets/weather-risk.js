(() => {
  const $ = id => document.getElementById(id);
  const city = $("weather-city");
  const status = $("weather-status");
  const button = $("weather-fetch");
  const result = $("weather-results");
  let lastSuccessfulRetrievedAt = null;
  if (!city || !status || !button || !result) return;

  const format = (value, digits = 1, suffix = "") => value !== null && value !== undefined && Number.isFinite(Number(value))
    ? `${Number(value).toFixed(digits)}${suffix}` : "Unavailable";
  const card = (label, value, unit = "") => `<article class="weather-stat"><div class="small">${label}</div><div class="value">${value}${unit}</div></article>`;

  function renderChart(rows) {
    const chart = $("weather-hourly-chart");
    chart.replaceChildren();
    const available = (rows || []).some(row => Number.isFinite(row.precipitation_mm));
    if (!available) {
      chart.textContent = "Hourly rainfall values are unavailable.";
      return;
    }
    const max = Math.max(1, ...rows.map(row => Number.isFinite(row.precipitation_mm) ? row.precipitation_mm : 0));
    for (const row of rows) {
      const hour = document.createElement("div");
      hour.className = "weather-hour";
      const bar = document.createElement("div");
      bar.className = "weather-hour-bar";
      const value = Number.isFinite(row.precipitation_mm) ? row.precipitation_mm : null;
      bar.style.height = value === null ? "2px" : `${Math.max(2, 100 * value / max)}%`;
      bar.title = `${row.time}: ${value === null ? "rain unavailable" : `${value.toFixed(1)} mm`}; precipitation probability ${row.precipitation_probability_pct ?? "unavailable"}%`;
      bar.setAttribute("aria-label", bar.title);
      hour.append(bar);
      const label = document.createElement("span");
      label.className = "weather-hour-label";
      label.textContent = row.time.slice(11, 16);
      hour.append(label);
      chart.append(hour);
    }
  }

  function render(data) {
    const grid = data.location.weather_grid;
    const weather = data.current_weather;
    const rainfall = data.rainfall;
    const risk = data.risk_assessment;
    const coords = `${data.location.selected_latitude.toFixed(4)}, ${data.location.selected_longitude.toFixed(4)}`;
    const gridText = grid.latitude == null ? "weather grid location unavailable" :
      `Forecast grid: ${grid.latitude.toFixed(3)}, ${grid.longitude.toFixed(3)} (${format(grid.distance_from_selected_km, 1, " km")} from selected coordinate)`;
    result.replaceChildren();
    const locationLine = document.createElement("p");
    locationLine.className = "small weather-risk-intro";
    locationLine.textContent = `${data.location.name} · selected coordinate ${coords} · ${gridText} · timezone ${data.timezone}`;
    result.append(locationLine);

    const stats = document.createElement("div");
    stats.className = "weather-risk-grid";
    stats.innerHTML = [
      card("Current temperature", format(weather.temperature_2m_c, 1, " °C")),
      card("Relative humidity", format(weather.relative_humidity_pct, 0, "%")),
      card("Wind speed", format(weather.wind_speed_10m_kmh, 1, " km/h")),
      card("Current condition", weather.weather_condition || "Unavailable"),
      card("Rainfall · next 3 hours", format(rainfall.next_3h_mm, 1, " mm")),
      card("Rainfall · next 24 hours", format(rainfall.next_24h_mm, 1, " mm")),
      card("Maximum hourly rainfall", format(rainfall.maximum_hourly_mm, 1, " mm/h")),
      card("Maximum precipitation probability", format(rainfall.maximum_precipitation_probability_pct, 0, "%")),
    ].join("");
    result.append(stats);

    const riskBox = document.createElement("section");
    riskBox.className = "weather-risk-result";
    riskBox.dataset.level = risk.level || "INSUFFICIENT";
    const heading = document.createElement("h3");
    heading.textContent = risk.level ? `${risk.level} · rainfall-based screening` : "Insufficient weather data for risk assessment.";
    riskBox.append(heading);
    const sub = document.createElement("p");
    sub.className = "small";
    sub.textContent = risk.message || "Insufficient weather data for risk assessment.";
    riskBox.append(sub);
    const reasons = document.createElement("ul");
    for (const reason of risk.reasons || []) {
      const item = document.createElement("li");
      item.textContent = reason;
      reasons.append(item);
    }
    riskBox.append(reasons);
    const rules = risk.thresholds || {};
    const ruleNote = document.createElement("p");
    ruleNote.className = "small";
    ruleNote.textContent = `Prototype rules (not official thresholds): MODERATE at ≥${rules.moderate_3h_mm} mm/3h, ≥${rules.moderate_24h_mm} mm/24h, or ≥${rules.moderate_hourly_mm} mm in the maximum-rain hour with same-hour precipitation probability ≥${rules.moderate_hourly_probability_pct}%; HIGH at ≥${rules.high_3h_mm} mm/3h, ≥${rules.high_24h_mm} mm/24h, or ≥${rules.high_hourly_mm} mm in that hour with same-hour probability ≥${rules.high_hourly_probability_pct}%.`;
    riskBox.append(ruleNote);
    result.append(riskBox);

    const chartTitle = document.createElement("h3");
    chartTitle.className = "weather-risk-intro";
    chartTitle.textContent = "Hourly rainfall forecast · next 24 hours";
    result.append(chartTitle);
    const chartWrap = document.createElement("div");
    chartWrap.className = "weather-chart-wrap";
    const chart = document.createElement("div");
    chart.id = "weather-hourly-chart";
    chart.className = "weather-chart";
    chart.setAttribute("role", "img");
    chart.setAttribute("aria-label", "Open-Meteo hourly precipitation forecast for the next 24 hours; bar tooltips show precipitation and precipitation probability.");
    chartWrap.append(chart);
    const axis = document.createElement("div");
    axis.className = "weather-chart-axis small";
    axis.innerHTML = "<span>0 mm</span><span>Bar height scales to maximum forecast hour</span>";
    chartWrap.append(axis);
    result.append(chartWrap);
    renderChart(data.hourly_forecast_next_24h);

    const metadata = document.createElement("p");
    metadata.className = "small weather-source";
    metadata.append(document.createTextNode(`Weather retrieval: ${data.retrieved_at} (UTC)${data.cache_hit ? ` · cached ${data.cache_age_seconds}s` : " · fresh API response"} · model current time: ${data.current_time} (${data.timezone}). Source: `));
    const sourceLink = document.createElement("a");
    sourceLink.href = "https://open-meteo.com/";
    sourceLink.target = "_blank";
    sourceLink.rel = "noreferrer";
    sourceLink.textContent = data.source.attribution;
    metadata.append(sourceLink, document.createTextNode(". The forecast model issue time was not supplied."));
    result.append(metadata);
  }

  async function loadWeather(forceRefresh = false) {
    const isManual = city.value === "manual";
    const manualFields = $("weather-manual-coordinates");
    manualFields.hidden = !isManual;
    let query;
    if (isManual) {
      const lat = Number($("weather-latitude").value);
      const lon = Number($("weather-longitude").value);
      if ($("weather-latitude").value.trim() === "" || !Number.isFinite(lat) || lat < -90 || lat > 90) { status.textContent = "Latitude must be between -90 and 90."; return; }
      if ($("weather-longitude").value.trim() === "" || !Number.isFinite(lon) || lon < -180 || lon > 180) { status.textContent = "Longitude must be between -180 and 180."; return; }
      query = new URLSearchParams({ lat: String(lat), lon: String(lon) });
    } else {
      query = new URLSearchParams({ city: city.value });
    }
    if (forceRefresh) query.set("refresh", "1");
    button.disabled = true;
    status.textContent = "Fetching real Open-Meteo forecast…";
    try {
      const response = await fetch(`/api/weather-risk?${query.toString()}`, { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Weather request failed (HTTP ${response.status}).`);
      render(data);
      lastSuccessfulRetrievedAt = data.retrieved_at;
      status.textContent = data.risk_assessment.status === "insufficient_data"
        ? "Weather response received, but its forecast values are incomplete."
        : "Forecast and screening updated from Open-Meteo.";
    } catch (error) {
      result.replaceChildren();
      const message = document.createElement("p");
      message.textContent = error.message;
      result.append(message);
      status.textContent = `Weather data unavailable; no values or screening result were substituted.${lastSuccessfulRetrievedAt ? ` Last successful retrieval: ${lastSuccessfulRetrievedAt} UTC.` : " No successful retrieval in this session."}`;
    } finally {
      button.disabled = false;
    }
  }

  async function init() {
    try {
      const response = await fetch("/api/weather-risk/locations", { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load supported India locations.");
      const data = await response.json();
      city.replaceChildren();
      for (const location of data.locations) {
        const option = document.createElement("option");
        option.value = location.id;
        option.textContent = location.name;
        city.append(option);
      }
      const manual = document.createElement("option");
      manual.value = "manual";
      manual.textContent = "Manual latitude / longitude";
      city.append(manual);
      city.value = "guwahati";
      await loadWeather(false);
    } catch (error) {
      status.textContent = `Weather module initialization failed: ${error.message}`;
    }
  }

  button.addEventListener("click", () => loadWeather(true));
  city.addEventListener("change", () => {
    $("weather-manual-coordinates").hidden = city.value !== "manual";
    if (city.value !== "manual") loadWeather(false);
  });
  init();
})();
