
(() => {
 'use strict';
 const form=document.getElementById('request-form');if(!form)return;
 const config=JSON.parse(form.dataset.request);form.hidden=false;
 let prepared='';
 const result=document.getElementById('request-result');
 form.addEventListener('input',()=>{prepared='';result.hidden=true;document.getElementById('request-email').removeAttribute('href')});
 form.addEventListener('submit',event=>{
  event.preventDefault();if(!form.reportValidity())return;
  const data=new FormData(form);
  const clean=value=>String(value||'').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g,'').trim();
  prepared=config.title+'\n\n'+config.intro+'\n\n'+Object.entries(config.labels).map(([key,label])=>label+': '+(clean(data.get(key))||config.blank)).join('\n')+'\n';
  document.getElementById('request-preview').textContent=prepared;
  document.getElementById('request-status').textContent=config.prepared;
  document.getElementById('request-email').setAttribute('href','mailto:prabhawa@wavervanir.com?subject='+encodeURIComponent('CBSRM '+config.kind+' discussion')+'&body='+encodeURIComponent(prepared));
  result.hidden=false;
 });
 document.getElementById('request-download').addEventListener('click',()=>{
  if(!prepared)return;
  const url=URL.createObjectURL(new Blob([prepared],{type:'text/plain;charset=utf-8'}));
  const anchor=document.createElement('a');anchor.href=url;anchor.download='CBSRM-'+config.kind+'-request.txt';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
})();
