function frame(w,h,id='') {
 const p=(n)=>`M${18+n} ${n}H${w-24-n}l${18} 18V${h-22-n}l-18 18H${20+n}L${n} ${h-24-n}V${22+n}Z`;
 return `<svg class="lm-frame" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path d="${p(1)}"/><path d="${p(6)}" opacity=".6"/><path d="${p(11)}" opacity=".32"/><path class="lm-hot-edge" d="M7 66V24L24 7H145M${w-105} 7h78l20 19v38M${w-7} ${h-118}v90l-21 21h-90M7 ${h-60}v33l20 20h74"/><path d="M155 2h63l7 5h70m${w-450} -5h71l8 5h44M50 ${h-3}h100l8-6h55"/>${Array.from({length:8},(_,i)=>`<path d="M${w-120+i*7} ${h-21}l5-5" stroke-width=".6" opacity=".45"/>`).join('')}<path stroke-dasharray="2 4" opacity=".6" d="M35 15h75M${w-100} ${h-16}h60"/></svg>`;
}

function reactor(blue=false) {
 return `<svg viewBox="0 0 110 110" class="lm-reactor ${blue?'blue':''}" aria-hidden="true"><g fill="none" stroke="currentColor"><circle cx="55" cy="55" r="51" stroke-width="1"/><circle cx="55" cy="55" r="47" stroke-width="2" stroke-dasharray="44 4 10 6"/><circle cx="55" cy="55" r="40" stroke-width="4" stroke-dasharray="25 3"/><circle cx="55" cy="55" r="33" stroke-width="1.5"/><path d="M55 2v10m0 86v10M2 55h10m86 0h10"/><path d="m27 31 56 0-28 51Z" stroke-width="3" fill="#16050a"/><path class="lm-reactor-white" d="m37 39 36 0-18 31Z" fill="currentColor" stroke="none"/><path d="m55 20-8 13h16ZM27 42l10 24 5-9Zm56 0L73 66l-5-9ZM45 77h20L55 92Z" class="lm-reactor-white" fill="currentColor" stroke="none"/></g></svg>`;
}

function gauge(color){return `<svg class="lm-gauge" viewBox="0 0 60 60" style="color:${color}" aria-hidden="true"><g fill="none" stroke="currentColor"><circle cx="30" cy="30" r="27" opacity=".35"/><circle cx="30" cy="30" r="23" stroke-width="3" stroke-dasharray="40 6 20 8"/><circle cx="30" cy="30" r="17" opacity=".7"/><circle cx="30" cy="30" r="9" stroke-width="2"/><circle cx="30" cy="30" r="4" fill="currentColor"/></g></svg>`;}

function circuits(w,h,seed=5){let rand=()=>{seed=(seed*16807)%2147483647;return seed/2147483647;};return `<svg class="lm-circuits" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">${Array.from({length:45},()=>{let x=rand()*w,y=rand()*h,dx=15+rand()*80;return `<path d="M${x} ${y}h${dx}l22-22h${dx*.5}" stroke="${rand()>.75?'#ec1230':'#5c1020'}" opacity="${.1+rand()*.32}" fill="none"/><circle cx="${x}" cy="${y}" r="${rand()> .85?2:0.6}" fill="#ff1537" opacity=".6"/>`;}).join('')}</svg>`;}

export {frame,reactor,gauge,circuits};
