/* Olimpia Splendid Sherpa Lovelace cards - generated, do not edit */
var xt=globalThis,bt=xt.ShadowRoot&&(xt.ShadyCSS===void 0||xt.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,It=Symbol(),Xt=new WeakMap,ct=class{constructor(t,e,s){if(this._$cssResult$=!0,s!==It)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o,e=this.t;if(bt&&t===void 0){let s=e!==void 0&&e.length===1;s&&(t=Xt.get(e)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),s&&Xt.set(e,t))}return t}toString(){return this.cssText}},wt=n=>new ct(typeof n=="string"?n:n+"",void 0,It),F=(n,...t)=>{let e=n.length===1?n[0]:t.reduce((s,i,r)=>s+(o=>{if(o._$cssResult$===!0)return o.cssText;if(typeof o=="number")return o;throw Error("Value passed to 'css' function must be a 'css' function result: "+o+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+n[r+1],n[0]);return new ct(e,n,It)},Jt=(n,t)=>{if(bt)n.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of t){let s=document.createElement("style"),i=xt.litNonce;i!==void 0&&s.setAttribute("nonce",i),s.textContent=e.cssText,n.appendChild(s)}},Pt=bt?n=>n:n=>n instanceof CSSStyleSheet?(t=>{let e="";for(let s of t.cssRules)e+=s.cssText;return wt(e)})(n):n;var{is:Re,defineProperty:Te,getOwnPropertyDescriptor:Ne,getOwnPropertyNames:Oe,getOwnPropertySymbols:Ie,getPrototypeOf:Pe}=Object,At=globalThis,Qt=At.trustedTypes,Ue=Qt?Qt.emptyScript:"",Le=At.reactiveElementPolyfillSupport,dt=(n,t)=>n,Ut={toAttribute(n,t){switch(t){case Boolean:n=n?Ue:null;break;case Object:case Array:n=n==null?n:JSON.stringify(n)}return n},fromAttribute(n,t){let e=n;switch(t){case Boolean:e=n!==null;break;case Number:e=n===null?null:Number(n);break;case Object:case Array:try{e=JSON.parse(n)}catch{e=null}}return e}},ee=(n,t)=>!Re(n,t),te={attribute:!0,type:String,converter:Ut,reflect:!1,useDefault:!1,hasChanged:ee};Symbol.metadata??=Symbol("metadata"),At.litPropertyMetadata??=new WeakMap;var M=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=te){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){let s=Symbol(),i=this.getPropertyDescriptor(t,s,e);i!==void 0&&Te(this.prototype,t,i)}}static getPropertyDescriptor(t,e,s){let{get:i,set:r}=Ne(this.prototype,t)??{get(){return this[e]},set(o){this[e]=o}};return{get:i,set(o){let l=i?.call(this);r?.call(this,o),this.requestUpdate(t,l,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??te}static _$Ei(){if(this.hasOwnProperty(dt("elementProperties")))return;let t=Pe(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(dt("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(dt("properties"))){let e=this.properties,s=[...Oe(e),...Ie(e)];for(let i of s)this.createProperty(i,e[i])}let t=this[Symbol.metadata];if(t!==null){let e=litPropertyMetadata.get(t);if(e!==void 0)for(let[s,i]of e)this.elementProperties.set(s,i)}this._$Eh=new Map;for(let[e,s]of this.elementProperties){let i=this._$Eu(e,s);i!==void 0&&this._$Eh.set(i,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){let e=[];if(Array.isArray(t)){let s=new Set(t.flat(1/0).reverse());for(let i of s)e.unshift(Pt(i))}else t!==void 0&&e.push(Pt(t));return e}static _$Eu(t,e){let s=e.attribute;return s===!1?void 0:typeof s=="string"?s:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),this.renderRoot!==void 0&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){let t=new Map,e=this.constructor.elementProperties;for(let s of e.keys())this.hasOwnProperty(s)&&(t.set(s,this[s]),delete this[s]);t.size>0&&(this._$Ep=t)}createRenderRoot(){let t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Jt(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,s){this._$AK(t,s)}_$ET(t,e){let s=this.constructor.elementProperties.get(t),i=this.constructor._$Eu(t,s);if(i!==void 0&&s.reflect===!0){let r=(s.converter?.toAttribute!==void 0?s.converter:Ut).toAttribute(e,s.type);this._$Em=t,r==null?this.removeAttribute(i):this.setAttribute(i,r),this._$Em=null}}_$AK(t,e){let s=this.constructor,i=s._$Eh.get(t);if(i!==void 0&&this._$Em!==i){let r=s.getPropertyOptions(i),o=typeof r.converter=="function"?{fromAttribute:r.converter}:r.converter?.fromAttribute!==void 0?r.converter:Ut;this._$Em=i;let l=o.fromAttribute(e,r.type);this[i]=l??this._$Ej?.get(i)??l,this._$Em=null}}requestUpdate(t,e,s,i=!1,r){if(t!==void 0){let o=this.constructor;if(i===!1&&(r=this[t]),s??=o.getPropertyOptions(t),!((s.hasChanged??ee)(r,e)||s.useDefault&&s.reflect&&r===this._$Ej?.get(t)&&!this.hasAttribute(o._$Eu(t,s))))return;this.C(t,e,s)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,e,{useDefault:s,reflect:i,wrapped:r},o){s&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,o??e??this[t]),r!==!0||o!==void 0)||(this._$AL.has(t)||(this.hasUpdated||s||(e=void 0),this._$AL.set(t,e)),i===!0&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[i,r]of this._$Ep)this[i]=r;this._$Ep=void 0}let s=this.constructor.elementProperties;if(s.size>0)for(let[i,r]of s){let{wrapped:o}=r,l=this[i];o!==!0||this._$AL.has(i)||l===void 0||this.C(i,void 0,r,l)}}let t=!1,e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(s=>s.hostUpdate?.()),this.update(e)):this._$EM()}catch(s){throw t=!1,this._$EM(),s}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};M.elementStyles=[],M.shadowRootOptions={mode:"open"},M[dt("elementProperties")]=new Map,M[dt("finalized")]=new Map,Le?.({ReactiveElement:M}),(At.reactiveElementVersions??=[]).push("2.1.2");var Bt=globalThis,se=n=>n,Et=Bt.trustedTypes,ie=Et?Et.createPolicy("lit-html",{createHTML:n=>n}):void 0,ce="$lit$",B=`lit$${Math.random().toFixed(9).slice(2)}$`,de="?"+B,He=`<${de}>`,q=document,pt=()=>q.createComment(""),ut=n=>n===null||typeof n!="object"&&typeof n!="function",Kt=Array.isArray,Me=n=>Kt(n)||typeof n?.[Symbol.iterator]=="function",Lt=`[ 	
\f\r]`,ht=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,ne=/-->/g,re=/>/g,V=RegExp(`>|${Lt}(?:([^\\s"'>=/]+)(${Lt}*=${Lt}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),oe=/'/g,ae=/"/g,he=/^(?:script|style|textarea|title)$/i,Gt=n=>(t,...e)=>({_$litType$:n,strings:t,values:e}),u=Gt(1),C=Gt(2),Qe=Gt(3),Z=Symbol.for("lit-noChange"),p=Symbol.for("lit-nothing"),le=new WeakMap,Y=q.createTreeWalker(q,129);function pe(n,t){if(!Kt(n)||!n.hasOwnProperty("raw"))throw Error("invalid template strings array");return ie!==void 0?ie.createHTML(t):t}var De=(n,t)=>{let e=n.length-1,s=[],i,r=t===2?"<svg>":t===3?"<math>":"",o=ht;for(let l=0;l<e;l++){let a=n[l],c,h,d=-1,v=0;for(;v<a.length&&(o.lastIndex=v,h=o.exec(a),h!==null);)v=o.lastIndex,o===ht?h[1]==="!--"?o=ne:h[1]!==void 0?o=re:h[2]!==void 0?(he.test(h[2])&&(i=RegExp("</"+h[2],"g")),o=V):h[3]!==void 0&&(o=V):o===V?h[0]===">"?(o=i??ht,d=-1):h[1]===void 0?d=-2:(d=o.lastIndex-h[2].length,c=h[1],o=h[3]===void 0?V:h[3]==='"'?ae:oe):o===ae||o===oe?o=V:o===ne||o===re?o=ht:(o=V,i=void 0);let y=o===V&&n[l+1].startsWith("/>")?" ":"";r+=o===ht?a+He:d>=0?(s.push(c),a.slice(0,d)+ce+a.slice(d)+B+y):a+B+(d===-2?l:y)}return[pe(n,r+(n[e]||"<?>")+(t===2?"</svg>":t===3?"</math>":"")),s]},$t=class n{constructor({strings:t,_$litType$:e},s){let i;this.parts=[];let r=0,o=0,l=t.length-1,a=this.parts,[c,h]=De(t,e);if(this.el=n.createElement(c,s),Y.currentNode=this.el.content,e===2||e===3){let d=this.el.content.firstChild;d.replaceWith(...d.childNodes)}for(;(i=Y.nextNode())!==null&&a.length<l;){if(i.nodeType===1){if(i.hasAttributes())for(let d of i.getAttributeNames())if(d.endsWith(ce)){let v=h[o++],y=i.getAttribute(d).split(B),m=/([.?@])?(.*)/.exec(v);a.push({type:1,index:r,name:m[2],strings:y,ctor:m[1]==="."?Mt:m[1]==="?"?Dt:m[1]==="@"?Wt:Q}),i.removeAttribute(d)}else d.startsWith(B)&&(a.push({type:6,index:r}),i.removeAttribute(d));if(he.test(i.tagName)){let d=i.textContent.split(B),v=d.length-1;if(v>0){i.textContent=Et?Et.emptyScript:"";for(let y=0;y<v;y++)i.append(d[y],pt()),Y.nextNode(),a.push({type:2,index:++r});i.append(d[v],pt())}}}else if(i.nodeType===8)if(i.data===de)a.push({type:2,index:r});else{let d=-1;for(;(d=i.data.indexOf(B,d+1))!==-1;)a.push({type:7,index:r}),d+=B.length-1}r++}}static createElement(t,e){let s=q.createElement("template");return s.innerHTML=t,s}};function J(n,t,e=n,s){if(t===Z)return t;let i=s!==void 0?e._$Co?.[s]:e._$Cl,r=ut(t)?void 0:t._$litDirective$;return i?.constructor!==r&&(i?._$AO?.(!1),r===void 0?i=void 0:(i=new r(n),i._$AT(n,e,s)),s!==void 0?(e._$Co??=[])[s]=i:e._$Cl=i),i!==void 0&&(t=J(n,i._$AS(n,t.values),i,s)),t}var Ht=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){let{el:{content:e},parts:s}=this._$AD,i=(t?.creationScope??q).importNode(e,!0);Y.currentNode=i;let r=Y.nextNode(),o=0,l=0,a=s[0];for(;a!==void 0;){if(o===a.index){let c;a.type===2?c=new ft(r,r.nextSibling,this,t):a.type===1?c=new a.ctor(r,a.name,a.strings,this,t):a.type===6&&(c=new zt(r,this,t)),this._$AV.push(c),a=s[++l]}o!==a?.index&&(r=Y.nextNode(),o++)}return Y.currentNode=q,i}p(t){let e=0;for(let s of this._$AV)s!==void 0&&(s.strings!==void 0?(s._$AI(t,s,e),e+=s.strings.length-2):s._$AI(t[e])),e++}},ft=class n{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,s,i){this.type=2,this._$AH=p,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=s,this.options=i,this._$Cv=i?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode,e=this._$AM;return e!==void 0&&t?.nodeType===11&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=J(this,t,e),ut(t)?t===p||t==null||t===""?(this._$AH!==p&&this._$AR(),this._$AH=p):t!==this._$AH&&t!==Z&&this._(t):t._$litType$!==void 0?this.$(t):t.nodeType!==void 0?this.T(t):Me(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==p&&ut(this._$AH)?this._$AA.nextSibling.data=t:this.T(q.createTextNode(t)),this._$AH=t}$(t){let{values:e,_$litType$:s}=t,i=typeof s=="number"?this._$AC(t):(s.el===void 0&&(s.el=$t.createElement(pe(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===i)this._$AH.p(e);else{let r=new Ht(i,this),o=r.u(this.options);r.p(e),this.T(o),this._$AH=r}}_$AC(t){let e=le.get(t.strings);return e===void 0&&le.set(t.strings,e=new $t(t)),e}k(t){Kt(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,s,i=0;for(let r of t)i===e.length?e.push(s=new n(this.O(pt()),this.O(pt()),this,this.options)):s=e[i],s._$AI(r),i++;i<e.length&&(this._$AR(s&&s._$AB.nextSibling,i),e.length=i)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){let s=se(t).nextSibling;se(t).remove(),t=s}}setConnected(t){this._$AM===void 0&&(this._$Cv=t,this._$AP?.(t))}},Q=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,s,i,r){this.type=1,this._$AH=p,this._$AN=void 0,this.element=t,this.name=e,this._$AM=i,this.options=r,s.length>2||s[0]!==""||s[1]!==""?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=p}_$AI(t,e=this,s,i){let r=this.strings,o=!1;if(r===void 0)t=J(this,t,e,0),o=!ut(t)||t!==this._$AH&&t!==Z,o&&(this._$AH=t);else{let l=t,a,c;for(t=r[0],a=0;a<r.length-1;a++)c=J(this,l[s+a],e,a),c===Z&&(c=this._$AH[a]),o||=!ut(c)||c!==this._$AH[a],c===p?t=p:t!==p&&(t+=(c??"")+r[a+1]),this._$AH[a]=c}o&&!i&&this.j(t)}j(t){t===p?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}},Mt=class extends Q{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===p?void 0:t}},Dt=class extends Q{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==p)}},Wt=class extends Q{constructor(t,e,s,i,r){super(t,e,s,i,r),this.type=5}_$AI(t,e=this){if((t=J(this,t,e,0)??p)===Z)return;let s=this._$AH,i=t===p&&s!==p||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,r=t!==p&&(s===p||i);i&&this.element.removeEventListener(this.name,this,s),r&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}},zt=class{constructor(t,e,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(t){J(this,t)}};var We=Bt.litHtmlPolyfillSupport;We?.($t,ft),(Bt.litHtmlVersions??=[]).push("3.3.3");var ue=(n,t,e)=>{let s=e?.renderBefore??t,i=s._$litPart$;if(i===void 0){let r=e?.renderBefore??null;s._$litPart$=i=new ft(t.insertBefore(pt(),r),r,void 0,e??{})}return i._$AI(n),i};var jt=globalThis,U=class extends M{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=ue(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return Z}};U._$litElement$=!0,U.finalized=!0,jt.litElementHydrateSupport?.({LitElement:U});var ze=jt.litElementPolyfillSupport;ze?.({LitElement:U});(jt.litElementVersions??=[]).push("4.2.2");var Ct="#0f1216";var tt="#26262a",K="#35353a",et="#f2f2f7",gt="#8e8e93";var $e="#b9b02f";var I="#6edc96",fe="#79828f",ge="#e0392c",X="#0b2413",E={heatSupply:"#ff8a3d",heatReturn:"#c98a5f",coolSupply:"#19afff",coolReturn:"#5f9fc4",dhw:"#ff5d73",dhwReturn:"#c46a78"},R={bright:"#e6e6ea",light:"#d7d7db",mid:"#c9c9ce",dim:"#8f8f95",dark:"#6a6a6f",darker:"#5d5d61",track:"#3a3a40"},st={canvas:"18px",pill:"13px",button:"12px",chip:"999px"},Be=900,Ke=500,me=Be/Ke,Ft=Math.round(3*me*10)/10,G=Math.round(1.4*me*10)/10,mt=Math.round(G*.9*10)/10,_e="12px",ye="500";var f=n=>wt(n);function L(n,t){let e=t?n?.states[t]:void 0;if(!(!e||e.state==="unavailable"||e.state==="unknown"))return e.state}function x(n,t){let e=L(n,t);if(e===void 0)return;let s=Number(e);return Number.isFinite(s)?s:void 0}function k(n,t){return L(n,t)==="on"}function j(n,t,e){return n?.states[t]?.attributes?.[e]}function b(n,t=1){return n==null||!Number.isFinite(n)?"\u2014":n.toFixed(t)}var _t="sherpa";function kt(n=_t){let t=s=>`sensor.${n}_${s}`,e=s=>`binary_sensor.${n}_${s}`;return{climate:`climate.${n}_heat_pump`,waterIn:t("water_in"),waterOut:t("water_out"),dhwTank:t("dhw_tank"),outdoor:t("outdoor_air"),mode:t("mode"),waterTarget:t("water_target"),errorCode:t("error_code"),overrideCode:t("override_code"),pumpDuty:t("pump_duty"),heatingSetpoint:t("heating_setpoint"),coolingSetpoint:t("cooling_setpoint"),dhwSetpoint:t("dhw_setpoint"),compressor:e("compressor_running"),defrost:e("defrost"),pump:e("out_pump"),eh1:e("out_eh1"),eh2:e("out_eh2"),k5:e("out_k5"),boiler:e("out_boiler"),night:e("mode_night"),error:e("error"),warning:e("warning"),heatingCurve:e("heating_curve_enabled"),coolingCurve:e("cooling_curve_enabled"),number:s=>`number.${n}_${s}`,switch:s=>`switch.${n}_${s}`}}var Ge={title:"Heat pump",outdoorUnit:"Outdoor unit",indoorUnit:"Indoor unit",circuit:"Heating circuit",coolingCircuit:"Cooling circuit",tank:"Hot water",compressor:"Compressor",pump:"Pump",defrost:"Defrost",night:"Night",target:"target",calculated:"calculated from the curve",fixed:"fixed setpoint",supply:"Supply",return:"Return",outdoor:"Outdoor",set:"set",off:"Off",heat:"Heating",cool:"Cooling",standby:"Standby",heating:"Heating",cooling:"Cooling",domestic_hot_water:"Hot water",anti_legionella:"Anti-legionella",idle:"Idle",running:"Running",defrosting:"Defrosting",modeOnPanel:"The mode is set on the unit's panel.",heatingCurve:"Heating curve",coolingCurve:"Cooling curve",curveOff:"curve off",setpoints:"Setpoints",heatingSetpoint:"Heating",coolingSetpoint:"Cooling",dhwSetpoint:"Hot water",readOnly:"Read-only: writes are off, or this setpoint has not passed its write check.",noUnit:"No Sherpa entities found for prefix",on:"on"},je={title:"\u0422\u0435\u043F\u043B\u043E\u0432\u0438\u0439 \u043D\u0430\u0441\u043E\u0441",outdoorUnit:"\u0417\u043E\u0432\u043D\u0456\u0448\u043D\u0456\u0439 \u0431\u043B\u043E\u043A",indoorUnit:"\u0412\u043D\u0443\u0442\u0440\u0456\u0448\u043D\u0456\u0439 \u0431\u043B\u043E\u043A",circuit:"\u041A\u043E\u043D\u0442\u0443\u0440 \u043E\u043F\u0430\u043B\u0435\u043D\u043D\u044F",coolingCircuit:"\u041A\u043E\u043D\u0442\u0443\u0440 \u043E\u0445\u043E\u043B\u043E\u0434\u0436\u0435\u043D\u043D\u044F",tank:"\u0413\u0430\u0440\u044F\u0447\u0430 \u0432\u043E\u0434\u0430",compressor:"\u041A\u043E\u043C\u043F\u0440\u0435\u0441\u043E\u0440",pump:"\u041D\u0430\u0441\u043E\u0441",defrost:"\u0420\u043E\u0437\u043C\u043E\u0440\u043E\u0436\u0443\u0432\u0430\u043D\u043D\u044F",night:"\u041D\u0456\u0447",target:"\u0446\u0456\u043B\u044C",calculated:"\u0440\u043E\u0437\u0440\u0430\u0445\u043E\u0432\u0430\u043D\u043E \u0437\u0430 \u043A\u0440\u0438\u0432\u043E\u044E",fixed:"\u0444\u0456\u043A\u0441\u043E\u0432\u0430\u043D\u0430 \u0443\u0441\u0442\u0430\u0432\u043A\u0430",supply:"\u041F\u043E\u0434\u0430\u0447\u0430",return:"\u0417\u0432\u043E\u0440\u043E\u0442\u043A\u0430",outdoor:"\u041D\u0430\u0434\u0432\u043E\u0440\u0456",set:"\u0443\u0441\u0442\u0430\u0432\u043A\u0430",off:"\u0412\u0438\u043C\u043A\u043D\u0435\u043D\u043E",heat:"\u041E\u043F\u0430\u043B\u0435\u043D\u043D\u044F",cool:"\u041E\u0445\u043E\u043B\u043E\u0434\u0436\u0435\u043D\u043D\u044F",standby:"\u041E\u0447\u0456\u043A\u0443\u0432\u0430\u043D\u043D\u044F",heating:"\u041E\u043F\u0430\u043B\u0435\u043D\u043D\u044F",cooling:"\u041E\u0445\u043E\u043B\u043E\u0434\u0436\u0435\u043D\u043D\u044F",domestic_hot_water:"\u0413\u0430\u0440\u044F\u0447\u0430 \u0432\u043E\u0434\u0430",anti_legionella:"\u0410\u043D\u0442\u0438\u043B\u0435\u0433\u0456\u043E\u043D\u0435\u043B\u0430",idle:"\u041E\u0447\u0456\u043A\u0443\u0454",running:"\u041F\u0440\u0430\u0446\u044E\u0454",defrosting:"\u0420\u043E\u0437\u043C\u043E\u0440\u043E\u0436\u0443\u0432\u0430\u043D\u043D\u044F",modeOnPanel:"\u0420\u0435\u0436\u0438\u043C \u0437\u0430\u0434\u0430\u0454\u0442\u044C\u0441\u044F \u043D\u0430 \u043F\u0430\u043D\u0435\u043B\u0456 \u0430\u0433\u0440\u0435\u0433\u0430\u0442\u0443.",heatingCurve:"\u041A\u0440\u0438\u0432\u0430 \u043E\u043F\u0430\u043B\u0435\u043D\u043D\u044F",coolingCurve:"\u041A\u0440\u0438\u0432\u0430 \u043E\u0445\u043E\u043B\u043E\u0434\u0436\u0435\u043D\u043D\u044F",curveOff:"\u043A\u0440\u0438\u0432\u0430 \u0432\u0438\u043C\u043A\u043D\u0435\u043D\u0430",setpoints:"\u0423\u0441\u0442\u0430\u0432\u043A\u0438",heatingSetpoint:"\u041E\u043F\u0430\u043B\u0435\u043D\u043D\u044F",coolingSetpoint:"\u041E\u0445\u043E\u043B\u043E\u0434\u0436\u0435\u043D\u043D\u044F",dhwSetpoint:"\u0413\u0430\u0440\u044F\u0447\u0430 \u0432\u043E\u0434\u0430",readOnly:"\u041B\u0438\u0448\u0435 \u0447\u0438\u0442\u0430\u043D\u043D\u044F: \u0437\u0430\u043F\u0438\u0441 \u0432\u0438\u043C\u043A\u043D\u0435\u043D\u043E \u0430\u0431\u043E \u0446\u044F \u0443\u0441\u0442\u0430\u0432\u043A\u0430 \u043D\u0435 \u043F\u0440\u043E\u0439\u0448\u043B\u0430 \u043F\u0435\u0440\u0435\u0432\u0456\u0440\u043A\u0443 \u0437\u0430\u043F\u0438\u0441\u0443.",noUnit:"\u041D\u0435 \u0437\u043D\u0430\u0439\u0434\u0435\u043D\u043E \u0441\u0443\u0442\u043D\u043E\u0441\u0442\u0435\u0439 Sherpa \u0437 \u043F\u0440\u0435\u0444\u0456\u043A\u0441\u043E\u043C",on:"\u0443\u0432\u0456\u043C\u043A."};function St(n,t){return{...(n?.locale?.language||n?.language||"en").toLowerCase().startsWith("uk")?je:Ge,...t||{}}}function Yt(n){let t=[n?.outdoor_at_max_water,n?.max_water,n?.outdoor_at_min_water,n?.min_water];if(t.some(o=>o==null))return;let[e,s,i,r]=t;if(e!==i)return e<i?[[e,s],[i,r]]:[[i,r],[e,s]]}function ve(n,t){let e=Yt(n);if(!e)return;let[[s,i],[r,o]]=e;return t<=s?i:t>=r?o:i+(t-s)*(o-i)/(r-s)}function Rt(n){return u`<div class="sherpa-error">${n}</div>`}var Tt=F`
  :host {
    --sherpa-bg: var(--ha-card-background, var(--card-background-color, ${f(Ct)}));
    --sherpa-panel: var(--secondary-background-color, rgba(255, 255, 255, 0.06));
    --sherpa-text: var(--primary-text-color, ${f(et)});
    --sherpa-muted: var(--secondary-text-color, ${f(gt)});
    --sherpa-accent: var(--state-icon-active-color, ${f(I)});
    --sherpa-running: ${f(I)};
    --sherpa-warn: ${f($e)};
    --sherpa-fault: ${f(ge)};
    --sherpa-neutral: ${f(fe)};
    --sherpa-radius: ${f(st.canvas)};
    display: block;
  }

  ha-card {
    background: var(--sherpa-bg);
    color: var(--sherpa-text);
    border-radius: var(--sherpa-radius);
    padding: 16px;
    overflow: hidden;
  }

  .sherpa-error {
    padding: 12px;
    border-radius: 10px;
    background: color-mix(in srgb, var(--sherpa-fault) 15%, transparent);
    color: var(--sherpa-fault);
    font-size: 0.9rem;
  }

  .muted {
    color: var(--sherpa-muted);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
  }

  .title {
    font-size: 1.05rem;
    font-weight: 500;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: flex-end;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: ${f(st.chip)};
    font-size: 0.78rem;
    background: var(--sherpa-panel);
    color: var(--sherpa-text);
    white-space: nowrap;
  }

  .chip ha-icon {
    --mdc-icon-size: 15px;
  }

  .chip.running {
    background: var(--sherpa-running);
    color: ${f(X)};
  }

  .chip.warn {
    background: color-mix(in srgb, var(--sherpa-warn) 30%, transparent);
  }

  .chip.fault {
    background: color-mix(in srgb, var(--sherpa-fault) 25%, transparent);
    color: var(--sherpa-fault);
  }

  /* The one "value over artwork" pill, shared with the Futura cards. */
  .readout-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: ${f(st.pill)};
    background: rgba(12, 14, 18, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.2);
    padding: 4px 8px;
    font-size: ${f(_e)};
    font-weight: ${f(ye)};
    color: rgba(255, 255, 255, 0.92);
    font-variant-numeric: tabular-nums;
  }

  @media (prefers-reduced-motion: reduce) {
    * {
      animation: none !important;
      transition: none !important;
    }
  }
`;var Fe=1500,Ve=[{key:"heating_setpoint",label:"heatingSetpoint",sensor:n=>n.heatingSetpoint},{key:"cooling_setpoint",label:"coolingSetpoint",sensor:n=>n.coolingSetpoint},{key:"dhw_setpoint",label:"dhwSetpoint",sensor:n=>n.dhwSetpoint}],$={w:320,h:150,left:34,right:10,top:12,bottom:24},it=class extends U{constructor(){super(...arguments);this._draft={};this._timers={}}setConfig(e){if(!e)throw new Error("Invalid configuration");this._config={prefix:_t,show_curve:!0,show_setpoints:!0,...e}}static getStubConfig(){return{type:"custom:sherpa-control-card"}}getCardSize(){return 7}getGridOptions(){return{columns:6,rows:7,min_columns:4,min_rows:4}}disconnectedCallback(){super.disconnectedCallback(),Object.values(this._timers).forEach(e=>window.clearTimeout(e)),this._timers={}}get _ids(){return kt(this._config?.prefix)}render(){let e=this.hass,s=this._ids,i=St(e,this._config?.labels);if(!e||!e.states[s.climate])return u`<ha-card>${Rt(`${i.noUnit} "${this._config?.prefix}".`)}</ha-card>`;let r=L(e,s.climate)??"off",o=j(e,s.climate,"hvac_action"),l=j(e,s.climate,"dhw_in_progress"),a=x(e,s.waterTarget),c=j(e,s.waterTarget,"source"),h=r==="heat"?i.heat:r==="cool"?i.cool:i.off,d=l?i.domestic_hot_water:o==="heating"||o==="cooling"?i.running:o==="defrosting"?i.defrosting:o==="idle"?i.idle:void 0;return u`
      <ha-card>
        <div class="head">
          <span class="title">${this._config?.title??i.title}</span>
          <span class="chips">
            <span class="chip" title=${i.modeOnPanel}>
              <ha-icon icon="mdi:lock-outline"></ha-icon>${h}
            </span>
            ${d&&r!=="off"?u`<span class="chip ${o==="heating"||o==="cooling"?"running":o==="defrosting"?"warn":""}">${d}</span>`:p}
            ${k(e,s.night)?u`<span class="chip"><ha-icon icon="mdi:weather-night"></ha-icon>${i.night}</span>`:p}
          </span>
        </div>

        <div class="water">
          <div>
            <div class="big">${b(x(e,s.waterOut))}<span class="unit">°C</span></div>
            <div class="muted small">${i.supply}</div>
          </div>
          <div>
            <div class="mid">${b(a)}<span class="unit">°C</span></div>
            <div class="muted small" title=${c?.endsWith("_curve")?i.calculated:i.fixed}>${i.target}${c?.endsWith("_curve")?" *":""}</div>
          </div>
          <div>
            <div class="mid">${b(x(e,s.outdoor))}<span class="unit">°C</span></div>
            <div class="muted small">${i.outdoor}</div>
          </div>
        </div>

        ${this._config?.show_curve?this._curve(r==="cool"?"cooling":"heating",i,r!=="off"):p}
        ${c?.endsWith("_curve")?u`<div class="muted small foot">* ${i.calculated}</div>`:p}
        ${this._tank(i)}
        ${this._config?.show_setpoints?this._setpoints(i):p}
      </ha-card>
    `}_curve(e,s,i){let r=this.hass,o=this._ids,l=j(r,o.climate,`${e}_curve`),a=Yt(l),c=x(r,o.outdoor),h=x(r,e==="heating"?o.heatingSetpoint:o.coolingSetpoint),d=l?.enabled!==!1;if(!a)return u``;let[[v,y],[m,N]]=a,W=[v,m,...c===void 0?[]:[c]],rt=Math.min(...W)-5,ot=Math.max(...W)+5,at=[y,N,...h===void 0?[]:[h]],vt=Math.floor(Math.min(...at)-3),lt=Math.ceil(Math.max(...at)+3),z=O=>$.left+(O-rt)/(ot-rt)*($.w-$.left-$.right),P=O=>$.top+(lt-O)/(lt-vt)*($.h-$.top-$.bottom),Ot=e==="heating"?E.heatSupply:E.coolSupply,Ce=`M ${z(rt)} ${P(y)} L ${z(v)} ${P(y)} L ${z(m)} ${P(N)} L ${z(ot)} ${P(N)}`,Zt=c===void 0?void 0:d?ve(l,c):h,ke=[v,m,...c===void 0?[]:[Math.round(c)]],Se=[y,N];return u`
      <div class="section">
        <div class="row">
          <span>${e==="heating"?s.heatingCurve:s.coolingCurve}</span>
          ${d?p:u`<span class="chip">${s.curveOff}</span>`}
        </div>
        <svg class="chart" viewBox="0 0 ${$.w} ${$.h}" role="img"
             aria-label=${e==="heating"?s.heatingCurve:s.coolingCurve}>
          <rect class="plot" x=${$.left} y=${$.top} width=${$.w-$.left-$.right}
                height=${$.h-$.top-$.bottom} rx="6" />
          ${Se.map(O=>C`
            <line class="grid" x1=${$.left} x2=${$.w-$.right} y1=${P(O)} y2=${P(O)} />
            <text x=${$.left-6} y=${P(O)+4} text-anchor="end" class="tick">${b(O,0)}°</text>`)}
          ${ke.map(O=>C`
            <text x=${z(O)} y=${$.h-8} text-anchor="middle" class="tick">${b(O,0)}°</text>`)}
          <path d=${Ce} fill="none" stroke=${Ot} stroke-width="2.4"
                stroke-opacity=${d?1:.35} stroke-linejoin="round" />
          ${!d&&h!==void 0?C`
            <line x1=${$.left} x2=${$.w-$.right} y1=${P(h)} y2=${P(h)}
                  stroke=${Ot} stroke-width="2" stroke-dasharray="5 4" />`:p}
          ${c!==void 0&&Zt!==void 0?C`
            <line class="now" x1=${z(c)} x2=${z(c)} y1=${$.top}
                  y2=${$.h-$.bottom} />
            <circle class=${i?"point":"point hollow"} cx=${z(c)} cy=${P(Zt)} r="5"
                    style="--point:${Ot}" />`:p}
        </svg>
      </div>
    `}_tank(e){let s=this.hass,i=this._ids,r=x(s,i.dhwTank),o=x(s,i.dhwSetpoint),l=r===void 0||o===void 0||o<=0?0:Math.max(0,Math.min(1,r/o));return u`
      <div class="section">
        <div class="row">
          <span>${e.tank}</span>
          <span class="value">${b(r)} / ${b(o)} °C</span>
        </div>
        <div class="bar"><span style="width:${(l*100).toFixed(0)}%"></span></div>
      </div>
    `}_setpoints(e){let s=this.hass,i=this._ids,r=!1,o=Ve.map(l=>{let a=i.number(l.key),c=s?.states[a]!==void 0&&L(s,a)!==void 0;r||=!c;let h=this._draft[l.key]??(c?x(s,a):x(s,l.sensor(i)));return u`
        <div class="row setpoint">
          <span>${e[l.label]}</span>
          ${c?u`
            <span class="stepper">
              <button @click=${()=>this._step(l.key,a,-1)} aria-label="−">−</button>
              <span class="value ${this._draft[l.key]!==void 0?"pending":""}">${b(h)} °C</span>
              <button @click=${()=>this._step(l.key,a,1)} aria-label="+">+</button>
            </span>`:u`
            <span class="value" title=${e.readOnly}>
              ${b(h)} °C <ha-icon class="lock" icon="mdi:lock-outline"></ha-icon>
            </span>`}
        </div>
      `});return u`
      <div class="section">
        <div class="row"><span class="muted">${e.setpoints}</span></div>
        ${o}
        ${r?u`<div class="muted small">${e.readOnly}</div>`:p}
      </div>
    `}_step(e,s,i){let r=this.hass?.states[s];if(!r)return;let o=Number(r.attributes.step??.5),l=Number(r.attributes.min??-1/0),a=Number(r.attributes.max??1/0),c=this._draft[e]??Number(r.state);if(!Number.isFinite(c))return;let h=Math.round(Math.min(a,Math.max(l,c+i*o))/o)*o;this._draft={...this._draft,[e]:Number(h.toFixed(3))},window.clearTimeout(this._timers[e]),this._timers[e]=window.setTimeout(()=>this._send(e,s),Fe)}async _send(e,s){let i=this._draft[e];delete this._timers[e];try{i!==void 0&&i!==Number(this.hass?.states[s]?.state)&&await this.hass?.callService("number","set_value",{entity_id:s,value:i})}catch{}finally{let{[e]:r,...o}=this._draft;this._draft=o}}};it.properties={hass:{attribute:!1},_config:{state:!0},_draft:{state:!0}},it.styles=[Tt,F`
      .water {
        display: grid;
        grid-template-columns: 1.3fr 1fr 1fr;
        align-items: end;
        gap: 8px;
        margin-bottom: 12px;
        font-variant-numeric: tabular-nums;
      }

      .big {
        font-size: 2.1rem;
        font-weight: 400;
        line-height: 1.1;
      }

      .mid {
        font-size: 1.25rem;
        line-height: 1.2;
      }

      .unit {
        font-size: 0.55em;
        margin-left: 2px;
        color: var(--sherpa-muted);
      }

      .small {
        font-size: 0.75rem;
      }

      .foot {
        margin-top: 2px;
      }

      .section {
        margin-top: 10px;
      }

      .row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        font-size: 0.9rem;
      }

      .setpoint {
        padding: 5px 0;
        border-top: 1px solid var(--divider-color, ${f(K)});
      }

      .value {
        font-variant-numeric: tabular-nums;
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }

      .value.pending {
        color: var(--sherpa-accent);
      }

      .lock {
        --mdc-icon-size: 15px;
        color: var(--sherpa-muted);
      }

      .stepper {
        display: inline-flex;
        align-items: center;
        gap: 8px;
      }

      .stepper button {
        width: 30px;
        height: 30px;
        border-radius: ${f(st.button)};
        border: none;
        background: var(--sherpa-panel);
        color: var(--sherpa-text);
        font-size: 1.1rem;
        cursor: pointer;
      }

      .stepper button:hover {
        background: color-mix(in srgb, var(--sherpa-accent) 25%, var(--sherpa-panel));
      }

      .chart {
        display: block;
        width: 100%;
        height: auto;
        margin-top: 6px;
      }

      .tick {
        font-size: 10px;
        fill: var(--sherpa-muted);
      }

      /* The chart follows the theme: no fixed dark block on a light card. */
      .plot {
        fill: var(--sherpa-panel);
      }

      .grid {
        stroke: var(--divider-color, ${f(K)});
        stroke-width: 1;
      }

      .now {
        stroke: var(--sherpa-muted);
        stroke-width: 1;
        stroke-dasharray: 3 3;
        opacity: 0.7;
      }

      .point {
        fill: var(--point);
        stroke: var(--sherpa-bg);
        stroke-width: 2;
      }

      .point.hollow {
        fill: var(--sherpa-bg);
        stroke: var(--point);
      }

      .bar {
        height: 6px;
        border-radius: 3px;
        background: var(--sherpa-panel);
        margin-top: 6px;
        overflow: hidden;
      }

      .bar span {
        display: block;
        height: 100%;
        background: ${f(E.dhw)};
        border-radius: 3px;
      }
    `];var be=900,we=440,w={x:20,y:110,w:190,h:230},_={x:280,y:110,w:190,h:230},A={x:690,y:115,w:200,h:110},g={x:690,y:245,w:200,h:185},H={x:556,y:170},S={x:w.x+w.w/2,y:w.y+112,r:56},D={x:_.x+_.w/2,y:_.y+185,r:20},xe=[_.x+_.w/2-38,_.x+_.w/2+38].map(n=>({x:n,y:_.y+108})),qt=366,Nt=410,yt={supply:`M ${_.x+_.w} ${H.y} H ${H.x-16}`,toCircuit:`M ${H.x+16} ${H.y} H ${A.x}`,circuitReturn:`M ${A.x+A.w/2} ${A.y} V 60 H ${_.x+140} V ${_.y}`,toTank:`M ${H.x} ${H.y+16} V ${qt} H ${g.x+14}`,tankReturn:`M ${g.x+14} ${Nt} H ${_.x+50} V ${_.y+_.h}`},Ye=(()=>{let n=g.x+14,t=g.x+g.w-26,e=5,s=(t-n)/e,i=`M ${n} ${qt}`;for(let r=0;r<e;r+=1)i+=` q ${s/4} -14 ${s/2} 0 t ${s/2} 0`;i+=` C ${t+22} ${qt} ${t+22} ${Nt} ${t} ${Nt}`;for(let r=0;r<e;r+=1)i+=` q ${-s/4} 14 ${-s/2} 0 t ${-s/2} 0`;return i})();function T(n,t){return`left:${n/be*100}%;top:${t/we*100}%`}var nt=class extends U{setConfig(t){if(!t)throw new Error("Invalid configuration");this._config={prefix:_t,...t}}static getStubConfig(){return{type:"custom:sherpa-schematic-card"}}getCardSize(){return 6}getGridOptions(){return{columns:12,rows:6,min_columns:6,min_rows:4}}get _ids(){return kt(this._config?.prefix)}render(){let t=this.hass,e=this._ids,s=St(t,this._config?.labels);if(!t||!t.states[e.waterOut])return u`<ha-card>${Rt(`${s.noUnit} "${this._config?.prefix}".`)}</ha-card>`;let i=L(t,e.mode),r=L(t,e.climate),o=k(t,e.pump),l=k(t,e.compressor),a=i==="domestic_hot_water"||i==="anti_legionella"?"tank":r==="heat"||r==="cool"?"circuit":"none",c=r==="cool"?"cool":"heat",h=x(t,e.dhwTank),d=x(t,e.dhwSetpoint),v=x(t,e.waterTarget),y=j(t,e.waterTarget,"source"),m=L(t,e.errorCode),N=this._describe(e.errorCode,m),W=L(t,e.overrideCode),rt=this._describe(e.overrideCode,W),ot=a==="tank"?{x:H.x,y:268}:{x:(H.x+16+A.x)/2-8,y:H.y-30},at=a==="tank"?{x:590,y:Nt}:{x:600,y:60};return u`
      <ha-card>
        <div class="head">
          <span class="title">${this._config?.title??s.title}</span>
          <span class="chips">
            ${i?u`<span class="chip">${s[i]??i}</span>`:p}
            ${k(t,e.defrost)?u`<span class="chip warn"><ha-icon icon="mdi:snowflake-melt"></ha-icon>${s.defrost}</span>`:p}
            ${k(t,e.night)?u`<span class="chip"><ha-icon icon="mdi:weather-night"></ha-icon>${s.night}</span>`:p}
            ${k(t,e.eh1)?u`<span class="chip running">EH1</span>`:p}
            ${k(t,e.eh2)?u`<span class="chip running">EH2</span>`:p}
            ${k(t,e.k5)?u`<span class="chip running">K5</span>`:p}
          </span>
        </div>
        <div class="stage">
          ${this._drawing(a,c,o,l,h,d)}
          <span class="pill" style=${T(S.x,w.y+24)}>
            <span class="readout-pill"><ha-icon icon="mdi:thermometer"></ha-icon>${b(x(t,e.outdoor))} °C</span>
          </span>
          <span class="pill" style=${T(S.x,w.y+w.h-30)}>
            <span class="readout-pill">
              <span class="dot ${l?"on":""}"></span>${s.compressor}
            </span>
          </span>
          <span class="label strong" style=${T(w.x+w.w/2,w.y-18)}>${s.outdoorUnit}</span>
          <span class="label strong" style=${T(_.x+_.w/2,_.y+26)}>${s.indoorUnit}</span>
          ${xe.map((vt,lt)=>u`
            <span class="label tiny ${k(t,lt===0?e.eh1:e.eh2)?"on":""}" style=${T(vt.x,vt.y)}>EH${lt+1}</span>`)}
          <span class="pill" style=${T(ot.x,ot.y)}>
            <span class="readout-pill" title=${s.supply}><ha-icon icon="mdi:arrow-right-thin"></ha-icon>${b(x(t,e.waterOut))} °C</span>
          </span>
          <span class="pill" style=${T(at.x,at.y)}>
            <span class="readout-pill" title=${s.return}><ha-icon icon="mdi:arrow-left-thin"></ha-icon>${b(x(t,e.waterIn))} °C</span>
          </span>
          <span class="label strong" style=${T(A.x+A.w/2,A.y+32)}>
            ${c==="cool"?s.coolingCircuit:s.circuit}
          </span>
          <span class="pill" style=${T(A.x+A.w/2,A.y+74)}>
            <span class="readout-pill" title=${y?.endsWith("_curve")?s.calculated:s.fixed}>
              ${s.target} ${b(v)} °C${y?.endsWith("_curve")?" *":""}
            </span>
          </span>
          <span class="label strong" style=${T(g.x+g.w/2,g.y+26)}>${s.tank}</span>
          <span class="pill" style=${T(g.x+g.w/2,g.y+60)}>
            <span class="readout-pill big">${b(h)} °C</span>
          </span>
          <span class="label" style=${T(g.x+g.w/2,g.y+88)}>${s.set} ${b(d)} °C</span>
        </div>
        ${m&&m!=="none"?u`<div class="fault">${N}</div>`:p}
        ${W&&W!=="none"?u`<div class="override">${rt}</div>`:p}
        ${y?.endsWith("_curve")?u`<div class="foot muted">* ${s.calculated}</div>`:p}
      </ha-card>
    `}_describe(t,e){let s=j(this.hass,t,"descriptions")??{};return(e??"").split(",").map(i=>i.trim()).filter(Boolean).map(i=>s[i]?`${i} ${s[i]}`:i).join(" \xB7 ")}_drawing(t,e,s,i,r,o){let l=t==="tank"?{supply:E.dhw,back:E.dhwReturn}:e==="cool"?{supply:E.coolSupply,back:E.coolReturn}:{supply:E.heatSupply,back:E.heatReturn},a=R.track,c=(m,N,W)=>C`
      <path d=${m} fill="none" stroke=${N} stroke-width=${Ft}
            stroke-linecap="round" stroke-linejoin="round" />
      ${W?C`<path class="flow" d=${m} fill="none" stroke="#ffffff"
            stroke-opacity="0.45" stroke-width=${Ft*.45}
            stroke-dasharray="10 16" stroke-linecap="round" />`:p}
    `,h=t==="circuit",d=t==="tank",v=r===void 0||o===void 0||o<=15?0:Math.max(0,Math.min(1,(r-15)/(o-15))),y=g.h-8;return u`
      <svg viewBox="0 0 ${be} ${we}" role="img" aria-label="Sherpa schematic">
        <defs>
          <clipPath id="tank-clip">
            <rect x=${g.x+4} y=${g.y+4} width=${g.w-8} height=${y} rx="30" />
          </clipPath>
        </defs>

        <!-- refrigerant link -->
        ${[w.y+85,w.y+145].map(m=>C`
          <line x1=${w.x+w.w} y1=${m} x2=${_.x} y2=${m}
                stroke=${i?I:R.dark} stroke-opacity=${i?.7:1}
                stroke-width=${mt*1.6} stroke-dasharray=${i?"2 7":"none"}
                stroke-linecap="round" class=${i?"flow slow":""} />`)}

        <!-- pipes, idle first so the live route draws over the junctions -->
        ${c(yt.toCircuit,h?l.supply:a,h&&s)}
        ${c(yt.circuitReturn,h?l.back:a,h&&s)}
        ${c(yt.toTank,d?l.supply:a,d&&s)}
        ${c(yt.tankReturn,d?l.back:a,d&&s)}
        ${c(yt.supply,t==="none"?a:l.supply,t!=="none"&&s)}

        <!-- outdoor unit -->
        <rect x=${w.x} y=${w.y} width=${w.w} height=${w.h} rx="16"
              fill=${tt} stroke=${K} stroke-width=${G} />
        <circle cx=${S.x} cy=${S.y} r=${S.r} fill="none" stroke=${R.dark}
                stroke-width=${G} />
        <g class=${i?"spin":""} style="transform-origin:${S.x}px ${S.y}px">
          ${[0,120,240].map(m=>C`
            <ellipse cx=${S.x} cy=${S.y-28} rx="12" ry="27"
                     fill=${i?R.light:R.dim}
                     transform="rotate(${m} ${S.x} ${S.y})" />`)}
          <circle cx=${S.x} cy=${S.y} r="9" fill=${R.mid} />
        </g>

        <!-- indoor unit -->
        <rect x=${_.x} y=${_.y} width=${_.w} height=${_.h} rx="16"
              fill=${tt} stroke=${K} stroke-width=${G} />
        ${xe.map((m,N)=>C`
          <rect x=${m.x-28} y=${m.y-15} width="56" height="30" rx="8"
                fill=${k(this.hass,N===0?this._ids.eh1:this._ids.eh2)?I:"none"}
                stroke=${k(this.hass,N===0?this._ids.eh1:this._ids.eh2)?I:R.dark}
                stroke-width=${mt} />`)}
        <circle cx=${D.x} cy=${D.y} r=${D.r}
                fill=${s?I:"none"}
                stroke=${s?I:R.dim} stroke-width=${G} />
        <path d="M ${D.x-7} ${D.y-10} L ${D.x+11} ${D.y} L ${D.x-7} ${D.y+10} Z"
              fill=${s?X:R.dim} />

        <!-- three-way valve: inlet left, circuit right, tank down -->
        ${this._valve(h?l.supply:void 0,d?l.supply:void 0)}

        <!-- circuit -->
        <rect x=${A.x} y=${A.y} width=${A.w} height=${A.h} rx="14"
              fill=${tt} stroke=${h?l.supply:K}
              stroke-width=${G} />

        <!-- tank, filled as far as it has come up towards its setpoint -->
        <rect x=${g.x} y=${g.y} width=${g.w} height=${g.h} rx="34"
              fill=${tt} stroke=${d?E.dhw:K} stroke-width=${G} />
        <rect x=${g.x} y=${g.y+4+y*(1-v)} width=${g.w}
              height=${y*v} fill=${E.dhw} fill-opacity="0.16"
              clip-path="url(#tank-clip)" />
        <path d=${Ye} fill="none" stroke=${d?E.dhw:R.dark}
              stroke-width=${mt*1.4} stroke-linecap="round" />
      </svg>
    `}_valve(t,e){let{x:s,y:i}=H,r=16,o=(l,a)=>C`
      <polygon points=${l} fill=${a??tt}
               stroke=${a??R.dim} stroke-width=${mt} stroke-linejoin="round" />`;return C`
      ${o(`${s-r},${i-10} ${s-r},${i+10} ${s},${i}`,t??e)}
      ${o(`${s+r},${i-10} ${s+r},${i+10} ${s},${i}`,t)}
      ${o(`${s-10},${i+r} ${s+10},${i+r} ${s},${i}`,e)}
    `}};nt.properties={hass:{attribute:!1},_config:{state:!0}},nt.styles=[Tt,F`
      ha-card {
        background: ${f(Ct)};
        color: ${f(et)};
        --sherpa-text: ${f(et)};
        --sherpa-muted: ${f(gt)};
        --sherpa-panel: rgba(255, 255, 255, 0.08);
      }

      .stage {
        position: relative;
        container-type: inline-size;
      }

      svg {
        display: block;
        width: 100%;
        height: auto;
      }

      .pill,
      .label {
        position: absolute;
        transform: translate(-50%, -50%);
        white-space: nowrap;
        pointer-events: none;
      }

      .pill {
        pointer-events: auto;
      }

      .stage .readout-pill {
        font-size: min(12px, 2.36cqw);
        padding: 0.33em 0.67em;
        gap: 0.5em;
        border-radius: 1.1em;
      }

      .stage .readout-pill ha-icon {
        --mdc-icon-size: 1.1em;
      }

      .stage .readout-pill.big {
        font-size: min(14px, 2.75cqw);
      }

      .label {
        font-size: min(11px, 2.17cqw);
        color: ${f(gt)};
      }

      .label.strong {
        font-size: min(12px, 2.36cqw);
        color: ${f(et)};
      }

      .label.tiny {
        font-size: min(10px, 1.97cqw);
        font-weight: 500;
      }

      .label.tiny.on {
        color: ${f(X)};
      }

      .dot {
        width: 0.6em;
        height: 0.6em;
        border-radius: 50%;
        background: var(--sherpa-neutral);
      }

      .dot.on {
        background: var(--sherpa-running);
      }

      .fault,
      .override {
        margin-top: 10px;
        padding: 8px 10px;
        border-radius: 10px;
        font-size: 0.85rem;
      }

      .fault {
        background: color-mix(in srgb, var(--sherpa-fault) 22%, transparent);
        color: #ff7b70;
      }

      .override {
        background: color-mix(in srgb, var(--sherpa-warn) 25%, transparent);
      }

      .foot {
        margin-top: 6px;
        font-size: 0.75rem;
      }

      .flow {
        animation: flow 1.6s linear infinite;
      }

      .flow.slow {
        animation-duration: 3s;
      }

      .spin {
        animation: spin 1.4s linear infinite;
      }

      @keyframes flow {
        to {
          stroke-dashoffset: -52;
        }
      }

      @keyframes spin {
        to {
          transform: rotate(360deg);
        }
      }
    `];var Ee=[{type:"sherpa-schematic-card",name:"Sherpa schematic",description:"Outdoor and indoor unit, the three-way valve, the heating circuit and the hot-water tank, with the water route the heat pump is using now.",preview:!0,element:nt},{type:"sherpa-control-card",name:"Sherpa status and setpoints",description:"The mode as the panel has it, the water against its target, the climatic curve and the setpoints -- editable where the integration allows writes.",preview:!0,element:it}],Ae=window.customCards||=[];for(let n of Ee)if(customElements.get(n.type)||customElements.define(n.type,n.element),!Ae.some(t=>t.type===n.type)){let{element:t,...e}=n;Ae.push(e)}console.info(`%c SHERPA-CARDS %c ${Ee.length} cards registered `,`background:${I};color:${X}`,"");export{it as SherpaControlCard,nt as SherpaSchematicCard};
