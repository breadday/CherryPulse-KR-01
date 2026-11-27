const CherryPlusMarket = {
  async directory() {
    const response = await fetch("/data/symbols.json");
    if (!response.ok) throw new Error("DIRECTORY_UNAVAILABLE");
    return response.json();
  },
  async quote(code) {
    const response = await fetch("/api/quote?code=" + encodeURIComponent(code), {
      signal: AbortSignal.timeout(18000)
    });
    if (!response.ok) throw new Error("QUOTE_UNAVAILABLE");
    return response.json();
  }
};
