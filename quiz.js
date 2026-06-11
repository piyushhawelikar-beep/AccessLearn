const topicInput=document.getElementById('topicInput');
const genBtn=document.getElementById('generateQuizBtn');
const quizContainer=document.getElementById('quizContainer');
const result=document.getElementById('quizResult');
let questions=[];
genBtn?.addEventListener('click', async ()=>{
  result.textContent=''; quizContainer.innerHTML='Generating quiz...';
  const topic=topicInput.value || 'General Learning';
  const res=await fetch('/api/generate_quiz',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic})});
  const data=await res.json(); questions=data.questions; renderQuiz(topic);
});
function renderQuiz(topic){
  quizContainer.innerHTML='';
  questions.forEach((q,i)=>{
    const card=document.createElement('div'); card.className='question-card';
    card.innerHTML=`<h3>Q${i+1}. ${q.question}</h3>`+q.options.map((op,j)=>`<label class="option"><input type="radio" name="q${i}" value="${j}"> ${op}</label>`).join('')+`<p class="muted">${q.explanation}</p>`;
    quizContainer.appendChild(card);
  });
  const submit=document.createElement('button'); submit.className='btn'; submit.textContent='Submit Quiz';
  submit.onclick=()=>submitQuiz(topic); quizContainer.appendChild(submit);
}
async function submitQuiz(topic){
  let score=0;
  questions.forEach((q,i)=>{ const checked=document.querySelector(`input[name="q${i}"]:checked`); if(checked && Number(checked.value)===q.answer_index) score++; });
  result.textContent=`Your Score: ${score}/${questions.length}`;
  await fetch('/api/submit_quiz',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic,score,total_questions:questions.length})});
}
