const form = document.getElementById('chatForm');
const input = document.getElementById('messageInput');
const chatBox = document.getElementById('chatBox');
function addBubble(text, cls){ const div=document.createElement('div'); div.className=`bubble ${cls}`; div.textContent=text; chatBox.appendChild(div); chatBox.scrollTop=chatBox.scrollHeight; }
form?.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const msg=input.value.trim(); if(!msg) return;
  addBubble(msg,'user'); input.value=''; addBubble('Thinking...','bot');
  const res = await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})});
  const data = await res.json();
  chatBox.lastChild.textContent = data.reply;
});
