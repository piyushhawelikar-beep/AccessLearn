const btn = document.getElementById('summarizeBtn');
const input = document.getElementById('notesInput');
const output = document.getElementById('summaryOutput');
const fileInput = document.getElementById('summaryFile');
const urlInput = document.getElementById('summaryUrl');
const noteSelect = document.getElementById('summaryNote');
btn?.addEventListener('click', async ()=>{
  output.textContent='Generating smart summary...';
  const fd = new FormData();
  fd.append('text', input?.value || '');
  fd.append('url', urlInput?.value || '');
  fd.append('note_id', noteSelect?.value || '0');
  if(fileInput?.files?.[0]) fd.append('file', fileInput.files[0]);
  const res = await fetch('/api/summarize',{method:'POST', body: fd});
  const data = await res.json();
  output.textContent=data.summary;
});
