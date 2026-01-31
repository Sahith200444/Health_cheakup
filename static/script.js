console.log("AI Health Assistant Ready");

const form = document.querySelector("form");
const loader = document.getElementById("loader");
const progressText = document.getElementById("progress");

form.addEventListener("submit", function(){

  loader.style.display="flex";

  let percent=0;

  const interval=setInterval(()=>{
    if(percent<95){
      percent+=5;
      progressText.innerText = percent + "%";
    }
  },200);

  // Voice Feedback
  const msg = new SpeechSynthesisUtterance("Analyzing your health. Please wait.");
  speechSynthesis.speak(msg);
});
