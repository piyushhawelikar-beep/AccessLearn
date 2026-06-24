const form = document.getElementById('chatForm');
const input = document.getElementById('messageInput');
const chatBox = document.getElementById('chatBox');
const noteSelect = document.getElementById('noteSelect');
const suggestions = document.getElementById('suggestions');
function addBubble(text, cls){ const div=document.createElement('div'); div.className=`bubble ${cls}`; div.textContent=text; chatBox.appendChild(div); chatBox.scrollTop=chatBox.scrollHeight; }
function bindSuggestionButtons(){ document.querySelectorAll('.chip').forEach(btn=>{ btn.onclick=()=>{ input.value=btn.textContent; input.focus(); }; }); }
bindSuggestionButtons();
noteSelect?.addEventListener('change', async ()=>{
  const id = noteSelect.value;
  if(!id || id === '0') return;
  const res = await fetch(`/api/note-suggestions/${id}`);
  const data = await res.json();
  suggestions.innerHTML = data.questions.map(q=>`<button type="button" class="chip">${q}</button>`).join('');
  bindSuggestionButtons();
});
form?.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const msg=input.value.trim(); if(!msg) return;
  addBubble(msg,'user'); input.value=''; addBubble('Thinking...','bot');
  const res = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg, note_id: noteSelect?.value || 0})});
  const data = await res.json();
  chatBox.lastChild.textContent = data.reply;
});
