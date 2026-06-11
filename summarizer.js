const btn = document.getElementById('summarizeBtn');
const input = document.getElementById('notesInput');
const output = document.getElementById('summaryOutput');
btn?.addEventListener('click', async ()=>{
  output.textContent='Generating summary...';
  const res = await fetch('/api/summarize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:input.value})});
  const data = await res.json();
  output.textContent=data.summary;
});
