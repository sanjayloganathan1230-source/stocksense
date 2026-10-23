const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function buildUrl(path) {
  return `${API_BASE_URL.replace(/\/$/, '')}${path}`;
}

async function request(path, options = {}) {
  const response = await fetch(buildUrl(path), {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    try {
      const payload = JSON.parse(text);
      detail = payload.detail || payload.message || text;
    } catch (error) {
      // Ignore JSON parsing errors and use the raw response text.
    }

    throw new Error(detail || 'Request failed');
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }

  return response.text();
}

export const api = {
  async getSystemStatus() {
    return request('/api/system/status');
  },

  async getMarketStatus(exchange = 'NSE') {
    return request(`/api/market/status?exchange=${encodeURIComponent(exchange)}`);
  },

  async getQuote(symbol) {
    return request(`/api/market/quote/${encodeURIComponent(symbol.toUpperCase())}`);
  },

  async getIndexQuote(symbol) {
    return request(`/api/market/index/${encodeURIComponent(symbol.toUpperCase())}`);
  },

  async getHistoricalData(symbol, interval = '1d') {
    return request(`/api/market/historical/${encodeURIComponent(symbol.toUpperCase())}?interval=${encodeURIComponent(interval)}`);
  },

  async searchSymbols(query, limit = 8) {
    return request(`/api/market/search?query=${encodeURIComponent(query)}&limit=${encodeURIComponent(limit)}`);
  },

  async getMarketMovers() {
    return request('/api/market/movers');
  },

  async getMarketActivity() {
    return request('/api/market/activity');
  },
};
