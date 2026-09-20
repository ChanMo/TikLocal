document.addEventListener('DOMContentLoaded', async () => {
  const section = document.getElementById('similar-images-section');
  if (!section) return;
  try {
    const response = await fetch(`/api/recommend/similar?uri=${encodeURIComponent(section.dataset.uri)}&limit=12`);
    const result = await response.json();
    if (!response.ok || !result.success || !result.data?.indexed) return;
    const grid = document.getElementById('similar-images-grid');
    for (const item of result.data.items || []) {
      const link = document.createElement('a');
      link.href = item.detail_url;
      link.className = 'similar-image-card block overflow-hidden rounded-lg';
      const image = document.createElement('img');
      image.src = item.thumb_url;
      image.alt = item.name || '相似图片';
      image.loading = 'lazy';
      link.appendChild(image);
      grid.appendChild(link);
    }
    section.classList.toggle('is-visible', grid.childElementCount > 0);
  } catch (error) {
    section.classList.remove('is-visible');
  }
});
