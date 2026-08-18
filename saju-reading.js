// Vercel 서버리스 함수 — 브라우저는 이 주소(/api/saju-reading)만 호출하고,
// 실제 Anthropic API 키는 여기, 서버 환경변수에서만 읽습니다.
// 절대 이 파일에 키를 직접 적지 마세요 — Vercel 프로젝트 설정의
// Environment Variables에 ANTHROPIC_API_KEY로 등록해두면 자동으로 읽어옵니다.

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'POST 요청만 허용됩니다.' });
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: '서버에 API 키가 설정되지 않았습니다.' });
  }

  const { prompt, maxTokens } = req.body || {};
  if (!prompt || typeof prompt !== 'string') {
    return res.status(400).json({ error: 'prompt가 필요합니다.' });
  }

  try {
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-6',
        max_tokens: Math.min(Number(maxTokens) || 1500, 2000), // 남용 방지용 상한
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      return res.status(response.status).json({ error: data?.error?.message || '풀이를 불러오지 못했습니다.' });
    }

    // 프론트엔드가 기대하는 형태(data.content 배열) 그대로 전달
    return res.status(200).json(data);
  } catch (err) {
    return res.status(500).json({ error: '서버 오류가 발생했습니다.' });
  }
}
