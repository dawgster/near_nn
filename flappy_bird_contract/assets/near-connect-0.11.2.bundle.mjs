/* esm.sh - @hot-labs/near-connect@0.11.2 */
var Ie=Object.create;var de=Object.defineProperty;var _e=Object.getOwnPropertyDescriptor;var Me=Object.getOwnPropertyNames;var Ee=Object.getPrototypeOf,$e=Object.prototype.hasOwnProperty;var c=(s,e)=>()=>(e||s((e={exports:{}}).exports,e),e.exports);var We=(s,e,t,n)=>{if(e&&typeof e=="object"||typeof e=="function")for(let r of Me(e))!$e.call(s,r)&&r!==t&&de(s,r,{get:()=>e[r],enumerable:!(n=_e(e,r))||n.enumerable});return s};var Ne=(s,e,t)=>(t=s!=null?Ie(Ee(s)):{},We(e||!s||!s.__esModule?de(t,"default",{value:s,enumerable:!0}):t,s));var D=c(x=>{"use strict";Object.defineProperty(x,"__esModule",{value:!0});x.LocalStorage=void 0;var L=class{async get(e){return typeof window>"u"?null:localStorage.getItem(e)}async set(e,t){typeof window>"u"||localStorage.setItem(e,t)}async remove(e){typeof window>"u"||localStorage.removeItem(e)}};x.LocalStorage=L});var he=c(T=>{"use strict";Object.defineProperty(T,"__esModule",{value:!0});T.encodeBase58=je;var ue="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";function je(s){if(s.length===0)return"";let e=0,t=0;for(;t<s.length&&s[t]===0;)e++,t++;let n=[0];for(;t<s.length;t++){let o=s[t];for(let a=0;a<n.length;++a)o+=n[a]<<8,n[a]=o%58,o=o/58|0;for(;o>0;)n.push(o%58),o=o/58|0}for(;n.length>0&&n[n.length-1]===0;)n.pop();let r="";for(let o=0;o<e;o++)r+=ue[0];for(let o=n.length-1;o>=0;--o)r+=ue[n[o]];return r}});var p=c(v=>{"use strict";Object.defineProperty(v,"__esModule",{value:!0});v.nearActionsToConnectorActions=void 0;var Oe=he(),qe=s=>{try{return JSON.parse(new TextDecoder().decode(s))}catch{return s}},Le=s=>s.map(e=>{if("type"in e)return e;if(e.functionCall)return{type:"FunctionCall",params:{methodName:e.functionCall.methodName,args:qe(e.functionCall.args),gas:e.functionCall.gas.toString(),deposit:e.functionCall.deposit.toString()}};if(e.deployGlobalContract)return{type:"DeployGlobalContract",params:{code:e.deployGlobalContract.code,deployMode:e.deployGlobalContract.deployMode.AccountId?"AccountId":"CodeHash"}};if(e.createAccount)return{type:"CreateAccount"};if(e.useGlobalContract)return{type:"UseGlobalContract",params:{contractIdentifier:e.useGlobalContract.contractIdentifier.AccountId?{accountId:e.useGlobalContract.contractIdentifier.AccountId}:{codeHash:(0,Oe.encodeBase58)(e.useGlobalContract.contractIdentifier.CodeHash)}}};if(e.deployContract)return{type:"DeployContract",params:{code:e.deployContract.code}};if(e.deleteAccount)return{type:"DeleteAccount",params:{beneficiaryId:e.deleteAccount.beneficiaryId}};if(e.deleteKey)return{type:"DeleteKey",params:{publicKey:e.deleteKey.publicKey.toString()}};if(e.transfer)return{type:"Transfer",params:{deposit:e.transfer.deposit.toString()}};if(e.stake)return{type:"Stake",params:{stake:e.stake.stake.toString(),publicKey:e.stake.publicKey.toString()}};if(e.addKey)return{type:"AddKey",params:{publicKey:e.addKey.publicKey.toString(),accessKey:{nonce:Number(e.addKey.accessKey.nonce),permission:e.addKey.accessKey.permission.functionCall?{receiverId:e.addKey.accessKey.permission.functionCall.receiverId,allowance:e.addKey.accessKey.permission.functionCall.allowance?.toString(),methodNames:e.addKey.accessKey.permission.functionCall.methodNames}:"FullAccess"}}};throw new Error("Unsupported action type")});v.nearActionsToConnectorActions=Le});var C=c(k=>{"use strict";Object.defineProperty(k,"__esModule",{value:!0});k.uuid4=void 0;var De=()=>typeof window<"u"&&typeof window.crypto<"u"&&typeof window.crypto.randomUUID=="function"?window.crypto.randomUUID():"xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g,function(s){let e=Math.random()*16|0;return(s==="x"?e:e&3|8).toString(16)});k.uuid4=De});var U=c(S=>{"use strict";Object.defineProperty(S,"__esModule",{value:!0});S.ParentFrameWallet=void 0;var F=p(),Te=C(),K=class{connector;manifest;constructor(e,t){this.connector=e,this.manifest=t}callParentFrame(e,t){let n=(0,Te.uuid4)();return window.parent.postMessage({type:"near-wallet-injected-request",id:n,method:e,params:t},"*"),new Promise((r,o)=>{let a=i=>{i.data.type==="near-wallet-injected-response"&&i.data.id===n&&(window.removeEventListener("message",a),i.data.success?r(i.data.result):o(i.data.error))};window.addEventListener("message",a)})}async signIn(e){let t=await this.callParentFrame("near:signIn",{network:e?.network??this.connector.network,addFunctionCallKey:e?.addFunctionCallKey});return Array.isArray(t)?t:[t]}async signInAndSignMessage(e){let t=await this.callParentFrame("near:signInAndSignMessage",{network:e?.network??this.connector.network,addFunctionCallKey:e?.addFunctionCallKey,messageParams:e.messageParams});return Array.isArray(t)?t:[t]}async signOut(e){let t={...e,network:e?.network??this.connector.network};await this.callParentFrame("near:signOut",t)}async getAccounts(e){let t={...e,network:e?.network??this.connector.network};return this.callParentFrame("near:getAccounts",t)}async signAndSendTransaction(e){let t=(0,F.nearActionsToConnectorActions)(e.actions),n={...e,actions:t,network:e.network??this.connector.network};return this.callParentFrame("near:signAndSendTransaction",n)}async signAndSendTransactions(e){let t={...e,network:e.network??this.connector.network};return t.transactions=t.transactions.map(n=>({actions:(0,F.nearActionsToConnectorActions)(n.actions),receiverId:n.receiverId})),this.callParentFrame("near:signAndSendTransactions",t)}async signMessage(e){let t={...e,network:e.network??this.connector.network};return this.callParentFrame("near:signMessage",t)}async signDelegateActions(e){let t={...e,delegateActions:e.delegateActions.map(n=>({...n,actions:(0,F.nearActionsToConnectorActions)(n.actions)})),network:e.network||this.connector.network};return this.callParentFrame("near:signDelegateActions",t)}};S.ParentFrameWallet=K});var R=c(A=>{"use strict";Object.defineProperty(A,"__esModule",{value:!0});A.parseUrl=void 0;var Fe=s=>{try{return new URL(s)}catch{return null}};A.parseUrl=Fe});var B=c(P=>{"use strict";Object.defineProperty(P,"__esModule",{value:!0});P.EventEmitter=void 0;var z=class{events={};on(e,t){this.events[e]||(this.events[e]=[]),this.events[e].push(t)}emit(e,t){this.events[e]?.forEach(n=>n(t))}off(e,t){this.events[e]=this.events[e]?.filter(n=>n!==t)}once(e,t){let n=r=>{t(r),this.off(e,n)};this.on(e,n)}removeAllListeners(e){e?delete this.events[e]:this.events={}}};P.EventEmitter=z});var _=c(I=>{"use strict";Object.defineProperty(I,"__esModule",{value:!0});I.escapeHtml=we;I.html=Ke;function we(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;")}var H=Symbol("htmlTag");function Ke(s,...e){let t=s[0];for(let n=0;n<e.length;n++){for(let r of Array.isArray(e[n])?e[n]:[e[n]]){let o=r?.[H]?r[H]:we(String(r??""));t+=o}t+=s[n+1]}return Object.freeze({[H]:t,get html(){return t}})}});var ge=c(M=>{"use strict";Object.defineProperty(M,"__esModule",{value:!0});M.css=void 0;var Ue=s=>`
${s} * {
  box-sizing: border-box;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
  -ms-overflow-style: none; 
  scrollbar-width: none; 
  color: #fff;
}

${s} *::-webkit-scrollbar { 
  display: none;
}

${s} p,
${s} h1,
${s} h2,
${s} h3,
${s} h4,
${s} h5,
${s} h6 {
  margin: 0;
}

${s} .modal-container {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    z-index: 100000000;
    background-color: rgba(0, 0, 0, 0.5);
    display: flex;
    justify-content: center;
    align-items: center;
    flex-direction: column;
    transition: opacity 0.2s ease-in-out;
}

@media (max-width: 600px) {
  ${s} .modal-container {
    justify-content: flex-end;
  }
}

${s} .modal-content {
  display: flex;
  flex-direction: column;
  align-items: center;

  max-width: 420px;
  max-height: 615px;
  width: 100%;
  border-radius: 24px;
  background: #0d0d0d;
  border: 1.5px solid rgba(255, 255, 255, 0.1);
  transition: transform 0.2s ease-in-out;
}

@media (max-width: 600px) {
  ${s} .modal-content {
    max-width: 100%;
    width: 100%;
    max-height: 80%;
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
    border: none;
    border-top: 1.5px solid rgba(255, 255, 255, 0.1);
  }
}


${s} .modal-header {
  display: flex;
  padding: 16px;
  gap: 16px;
  align-self: stretch;
  align-items: center;
  justify-content: center;
  position: relative;
}

${s} .modal-header button {
  position: absolute;
  right: 16px;
  top: 16px;
  width: 32px;
  height: 32px;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.2s ease-in-out;
  border: none;
  background: none;
  display: flex;
  align-items: center;
  justify-content: center;
}

${s} .modal-header button:hover {
  background: rgba(255, 255, 255, 0.04);
}
  
${s} .modal-header p {
  color: #fff;
  text-align: center;
  font-size: 24px;
  font-style: normal;
  font-weight: 600;
  line-height: normal;
  margin: 0;
}


${s} .modal-body {
  display: flex;
  padding: 16px;
  flex-direction: column;
  align-items: flex-start;
  text-align: center;
  gap: 8px;
  overflow: auto;

  border-radius: 24px;
  background: rgba(255, 255, 255, 0.08);
  width: 100%;
  flex: 1;
}

${s} .modal-body textarea {
  width: 100%;
  padding: 12px;
  border-radius: 12px;
  background: #0d0d0d;
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.1);
  outline: none;
  font-size: 16px;
  transition: background 0.2s ease-in-out;
  font-family: monospace;
  font-size: 12px;
}

${s} .modal-body button {
  width: 100%;
  padding: 12px;
  border-radius: 12px;
  background: #fff;
  color: #000;
  border: none;
  cursor: pointer;
  font-size: 16px;
  transition: background 0.2s ease-in-out;
  margin-top: 16px;
}

${s} .footer {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 16px 24px;
  color: #fff;
  gap: 12px;
}

${s} .modal-body p {
  color: rgba(255, 255, 255, 0.9);
  text-align: center;
  font-size: 16px;
  font-style: normal;
  font-weight: 500;
  line-height: normal;
  letter-spacing: -0.8px;
}

${s} .footer img {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  object-fit: cover;
}

${s} .get-wallet-link {
  color: rgba(255, 255, 255, 0.5);
  text-align: center;
  font-size: 16px;
  font-style: normal;
  font-weight: 500;
  margin-left: auto;
  text-decoration: none;
  transition: color 0.2s ease-in-out;
  cursor: pointer;
}
  
${s} .get-wallet-link:hover {
  color: rgba(255, 255, 255, 1);
}


${s} .connect-item {
  display: flex;
  padding: 8px;
  align-items: center;
  gap: 12px;
  align-self: stretch;
  cursor: pointer;

  transition: background 0.2s ease-in-out;
  border-radius: 24px;
}

${s} .connect-item img {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  object-fit: cover;
  flex-shrink: 0;
}

${s} .connect-item-info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  text-align: left;
  flex: 1;
  margin-top: -2px;
}

${s} .connect-item-info .wallet-address {
  color: rgba(255, 255, 255, 0.5);
  font-size: 14px;
  font-style: normal;
  font-weight: 400;
  line-height: normal;
}

${s} .connect-item:hover {
  background: rgba(255, 255, 255, 0.04);
}

${s} .connect-item img {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  object-fit: cover;
}

${s} .connect-item p {
  color: rgba(255, 255, 255, 0.9);
  text-align: center;
  font-size: 18px;
  font-style: normal;
  font-weight: 600;
  line-height: normal;
  letter-spacing: -0.36px;
  margin: 0;
}
`;M.css=Ue});var G=c(E=>{"use strict";Object.defineProperty(E,"__esModule",{value:!0});E.Popup=void 0;var Re=ge(),ze=_(),fe=`n${Math.random().toString(36).substring(2,15)}`;if(typeof document<"u"){let s=document.createElement("style");s.textContent=(0,Re.css)(`.${fe}`),document.head.append(s)}var V=class{delegate;isClosed=!1;root=document.createElement("div");state={};constructor(e){this.delegate=e}get dom(){return(0,ze.html)``}disposables=[];addListener(e,t,n){let r=typeof e=="string"?this.root.querySelector(e):e;r&&(r.addEventListener(t,n),this.disposables.push(()=>r.removeEventListener(t,n)))}handlers(){this.disposables.forEach(n=>n()),this.disposables=[];let e=this.root.querySelector(".modal-container"),t=this.root.querySelector(".modal-content");t.onclick=n=>n.stopPropagation(),e.onclick=()=>{this.delegate.onReject(),this.destroy()}}update(e){this.state={...this.state,...e},this.root.innerHTML=this.dom.html,this.handlers()}create({show:e=!0}){this.root.className=`${fe} hot-connector-popup`,this.root.innerHTML=this.dom.html,document.body.append(this.root),this.handlers();let t=this.root.querySelector(".modal-container"),n=this.root.querySelector(".modal-content");n.style.transform="translateY(50px)",t.style.opacity="0",this.root.style.display="none",e&&setTimeout(()=>this.show(),10)}show(){let e=this.root.querySelector(".modal-container"),t=this.root.querySelector(".modal-content");t.style.transform="translateY(50px)",e.style.opacity="0",this.root.style.display="block",setTimeout(()=>{t.style.transform="translateY(0)",e.style.opacity="1"},100)}hide(){let e=this.root.querySelector(".modal-container"),t=this.root.querySelector(".modal-content");t.style.transform="translateY(50px)",e.style.opacity="0",setTimeout(()=>{this.root.style.display="none"},200)}destroy(){this.isClosed||(this.isClosed=!0,this.hide(),setTimeout(()=>{this.root.remove()},200))}};E.Popup=V});var me=c($=>{"use strict";Object.defineProperty($,"__esModule",{value:!0});$.IframeWalletPopup=void 0;var J=_(),Be=G(),Y=class extends Be.Popup{delegate;constructor(e){super(e),this.delegate=e}handlers(){super.handlers(),this.addListener("button","click",()=>this.delegate.onApprove())}create(){super.create({show:!1}),this.root.querySelector(".modal-body").appendChild(this.delegate.iframe),this.delegate.iframe.style.width="100%",this.delegate.iframe.style.height="720px",this.delegate.iframe.style.border="none"}get footer(){if(!this.delegate.footer)return"";let{icon:e,heading:t}=this.delegate.footer;return(0,J.html)`
      <div class="footer">
        ${e?(0,J.html)`<img src="${e}" alt="${t}" />`:""}
        <p>${t}</p>
      </div>
    `}get dom(){return(0,J.html)`<div class="modal-container">
      <div class="modal-content">
        <div class="modal-body" style="padding: 0; overflow: auto;"></div>
        ${this.footer}
      </div>
    </div>`}};$.IframeWalletPopup=Y});var pe=c(W=>{"use strict";Object.defineProperty(W,"__esModule",{value:!0});W.NEAR_CONNECT_VERSION=void 0;W.NEAR_CONNECT_VERSION="0.11.2"});var ye=c(X=>{"use strict";Object.defineProperty(X,"__esModule",{value:!0});var He=pe();async function Ve(s){let e=await s.executor.getAllStorage(),t=s.executor.connector.providers,n=s.executor.manifest,r=s.id,o=s.code.replaceAll(".localStorage",".sandboxedLocalStorage").replaceAll("window.top","window.selector").replaceAll("window.open","window.selector.open");return`
  <!DOCTYPE html>
  <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body>
      <div id="root"></div>

      <style>
        :root {
          --background-color: rgb(40, 40, 40);
          --text-color: rgb(255, 255, 255);
          --border-color: rgb(209, 209, 209);
        }

        * {
          font-family: system-ui, Avenir, Helvetica, Arial, sans-serif
        }

        body, html {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
          background-color: var(--background-color);
          color: var(--text-color);
        }

        #root {
          display: none;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100vh;
          width: 100vw;
          background: radial-gradient(circle at center, #2c2c2c 0%, #1a1a1a 100%);
          text-align: center;
        }

        #root * {
          box-sizing: border-box;
          font-family: Inter, system-ui, Avenir, Helvetica, Arial, sans-serif;
          line-height: 1.5;
          color-scheme: light dark;
          color: rgb(255, 255, 255);
          font-synthesis: none;
          text-rendering: optimizeLegibility;
          -webkit-font-smoothing: antialiased;
        }

        .prompt-container img {
          width: 100px;
          height: 100px;
          object-fit: cover;
          border-radius: 12px;
        }

        .prompt-container h1 {
          margin: 0;
          font-size: 24px;
          font-weight: 600;
          margin-top: 16px;
        }

        .prompt-container p {
          margin: 0;
          font-size: 16px;
          font-weight: 500;
          color: rgb(209, 209, 209);
        }

        .prompt-container button {
          background-color: #131313;
          border: none;
          border-radius: 12px;
          padding: 12px 24px;
          cursor: pointer;
          transition: border-color 0.25s;
          color: #fff;
          outline: none;
          font-size: 14px;
          font-weight: 500;
          font-family: inherit;
          margin-top: 16px;
        }
      </style>


      <script>
      window.sandboxedLocalStorage = (() => {
        let storage = ${JSON.stringify(e)}

        return {
          setItem: function(key, value) {
            window.selector.storage.set(key, value)
            storage[key] = value || '';
          },
          getItem: function(key) {
            return key in storage ? storage[key] : null;
          },
          removeItem: function(key) {
            window.selector.storage.remove(key)
            delete storage[key];
          },
          get length() {
            return Object.keys(storage).length;
          },
          key: function(i) {
            const keys = Object.keys(storage);
            return keys[i] || null;
          },
        };
      })();

      const showPrompt = async (args) => {
        const root = document.getElementById("root");   
        root.style.display = "flex";
        root.innerHTML = \`
          <div class="prompt-container">
            <img src="${n.icon}" />
            <h1>${n.name}</h1>
            <p>\${args.title}</p>
            <button>\${args.button}</button>
          </div>
        \`;

        return new Promise((resolve) => {
          root.querySelector("button")?.addEventListener("click", () => {
            root.innerHTML = "";
            resolve(true);
          });
        });
      }

      class ProxyWindow {
        constructor(url, features) {
          this.closed = false;
          this.windowIdPromise = window.selector.call("open", { url, features });

          window.addEventListener("message", async (event) => {            
            if (event.data.origin !== "${r}") return;
            if (!event.data.method?.startsWith("proxy-window:")) return;
            const method = event.data.method.replace("proxy-window:", "");
            if (method === "closed" && event.data.windowId === await this.id()) this.closed = true;
          });
        } 

        async id() {
          return await this.windowIdPromise;
        }

        async focus() {
          await window.selector.call("panel.focus", { windowId: await this.id() });
        }

        async postMessage(data) {
          window.selector.call("panel.postMessage", { windowId: await this.id(), data });
        }

        async close() {
          await window.selector.call("panel.close", { windowId: await this.id() });
        }
      }

      window.selector = {
        wallet: null,
        location: "${window.location.href}",
        nearConnectVersion: "${He.NEAR_CONNECT_VERSION}",
        
        outerHeight: ${window.outerHeight},
        screenY: ${window.screenY},
        outerWidth: ${window.outerWidth},
        screenX: ${window.screenX},

        providers: {
          mainnet: ${JSON.stringify(t.mainnet)},
          testnet: ${JSON.stringify(t.testnet)},
        },

        uuid() {
          return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
            const r = (Math.random() * 16) | 0;
            const v = c === "x" ? r : (r & 0x3) | 0x8;
            return v.toString(16);
          });
        },

        walletConnect: {
          connect(params) {
            return window.selector.call("walletConnect.connect", params);
          },
          disconnect(params) {
            return window.selector.call("walletConnect.disconnect", params);
          },
          request(params) {
            return window.selector.call("walletConnect.request", params);
          },
          getProjectId() {
            return window.selector.call("walletConnect.getProjectId", {});
          },
          getSession() {
            return window.selector.call("walletConnect.getSession", {});
          },
        },
      
        async ready(wallet) {
          wallet.manifest = ${JSON.stringify(n)};
          window.parent.postMessage({ method: "wallet-ready", origin: "${r}" }, "*");
          window.selector.wallet = wallet;
        },

        async call(method, params) {
          const id = window.selector.uuid();
          window.parent.postMessage({ method, params, id, origin: "${r}" }, "*");

          return new Promise((resolve, reject) => {
            const handler = (event) => {
              if (event.data.id !== id || event.data.origin !== "${r}") return;
              window.removeEventListener("message", handler);

              if (event.data.status === "failed") reject(event.data.result);
              else resolve(event.data.result);
            };

            window.addEventListener("message", handler);
          });
        },

        panelClosed(windowId) {
          window.parent.postMessage({ 
            method: "panel.closed", 
            origin: "${r}", 
            result: { windowId } 
          }, "*");
        },

        open(url, _, params) {
          return new ProxyWindow(url, params)
        },

        external(entity, key, ...args) {
          return window.selector.call("external", { entity, key, args: args || [] });
        },

        openNativeApp(url) {
          return window.selector.call("open.nativeApp", { url });
        },

        ui: {
          async whenApprove(options) {
            window.selector.ui.showIframe();
            await showPrompt(options);
            window.selector.ui.hideIframe();
          },

          async showIframe() {
            return await window.selector.call("ui.showIframe");
          },

          async hideIframe() {
            return await window.selector.call("ui.hideIframe");
          },
        },

        storage: {
          async set(key, value) {
            await window.selector.call("storage.set", { key, value });
          },
      
          async get(key) {
            return await window.selector.call("storage.get", { key });
          },
      
          async remove(key) {
            await window.selector.call("storage.remove", { key });
          },

          async keys() {
            return await window.selector.call("storage.keys", {});
          },
        },
      };

      window.addEventListener("message", async (event) => {
        if (event.data.origin !== "${r}") return;
        if (!event.data.method?.startsWith("wallet:")) return;
      
        const wallet = window.selector.wallet;
        const method = event.data.method.replace("wallet:", "");
        const payload = { id: event.data.id, origin: "${r}", method };
      
        if (wallet == null || typeof wallet[method] !== "function") {
          const data = { ...payload, status: "failed", result: "Method not found" };
          window.parent.postMessage(data, "*");
          return;
        }
        
        try {
          const result = await wallet[method](event.data.params);
          window.parent.postMessage({ ...payload, status: "success", result }, "*");
        } catch (error) {
          const data = { ...payload, status: "failed", result: error };
          window.parent.postMessage(data, "*");
        }
      });
      <\/script>

      <script type="module">${o}<\/script>
    </body>
  </html>
    `}X.default=Ve});var be=c(y=>{"use strict";var Ge=y&&y.__importDefault||function(s){return s&&s.__esModule?s:{default:s}};Object.defineProperty(y,"__esModule",{value:!0});var Je=B(),Ye=C(),Xe=me(),Qe=Ge(ye()),Q=class{executor;origin;iframe=document.createElement("iframe");events=new Je.EventEmitter;popup;handler;readyPromiseResolve;readyPromise=new Promise(e=>{this.readyPromiseResolve=e});constructor(e,t,n){this.executor=e,this.origin=(0,Ye.uuid4)(),this.handler=o=>{o.data.origin===this.origin&&(o.data.method==="wallet-ready"&&this.readyPromiseResolve(),n(this,o))},window.addEventListener("message",this.handler);let r=[];this.executor.checkPermissions("usb")&&r.push("usb *;"),this.executor.checkPermissions("hid")&&r.push("hid *;"),this.executor.checkPermissions("clipboardRead")&&r.push("clipboard-read;"),this.executor.checkPermissions("clipboardWrite")&&r.push("clipboard-write;"),this.executor.checkPermissions("bluetooth")&&r.push("bluetooth *;"),this.iframe.allow=r.join(" "),this.iframe.setAttribute("sandbox","allow-scripts"),(0,Qe.default)({id:this.origin,executor:this.executor,code:t}).then(o=>{this.executor.connector.logger?.log("Iframe code injected"),this.iframe.srcdoc=o}),this.popup=new Xe.IframeWalletPopup({footer:this.executor.connector.footerBranding,iframe:this.iframe,onApprove:()=>{},onReject:()=>{window.removeEventListener("message",this.handler),this.events.emit("close",{}),this.popup.destroy()}}),this.popup.create()}on(e,t){this.events.on(e,t)}show(){this.popup.show()}hide(){this.popup.hide()}postMessage(e){if(!this.iframe.contentWindow)throw new Error("Iframe not loaded");this.iframe.contentWindow.postMessage({...e,origin:this.origin},"*")}dispose(){window.removeEventListener("message",this.handler),this.popup.destroy()}};y.default=Q});var xe=c(b=>{"use strict";var Ze=b&&b.__importDefault||function(s){return s&&s.__esModule?s:{default:s}};Object.defineProperty(b,"__esModule",{value:!0});var g=R(),Z=C(),et=Ze(be()),tt=(0,Z.uuid4)(),ee=class{connector;manifest;activePanels={};storageSpace;constructor(e,t){this.connector=e,this.manifest=t,this.storageSpace=t.id}checkPermissions(e,t){if(e==="walletConnect")return!!this.manifest.permissions.walletConnect;if(e==="external"){let n=this.manifest.permissions.external;return!n||!t?.entity?!1:n.includes(t.entity)}if(e==="allowsOpen"){let n=(0,g.parseUrl)(t?.url||""),r=this.manifest.permissions.allowsOpen;return!n||!r||!Array.isArray(r)||r.length===0?!1:r.some(a=>{let i=(0,g.parseUrl)(a);return!(!i||n.protocol!==i.protocol||i.hostname&&n.hostname!==i.hostname||i.pathname&&i.pathname!=="/"&&n.pathname!==i.pathname)})}return this.manifest.permissions[e]}assertPermissions(e,t,n){if(!this.checkPermissions(t,n.data.params))throw e.postMessage({...n.data,status:"failed",result:"Permission denied"}),new Error("Permission denied")}_onMessage=async(e,t)=>{let n=o=>{e.postMessage({...t.data,status:"success",result:o})},r=o=>{e.postMessage({...t.data,status:"failed",result:o})};if(t.data.method==="ui.showIframe"){e.show(),n(null);return}if(t.data.method==="ui.hideIframe"){e.hide(),n(null);return}if(t.data.method==="storage.set"){this.assertPermissions(e,"storage",t),localStorage.setItem(`${this.storageSpace}:${t.data.params.key}`,t.data.params.value),n(null);return}if(t.data.method==="storage.get"){this.assertPermissions(e,"storage",t);let o=localStorage.getItem(`${this.storageSpace}:${t.data.params.key}`);n(o);return}if(t.data.method==="storage.keys"){this.assertPermissions(e,"storage",t);let o=Object.keys(localStorage).filter(a=>a.startsWith(`${this.storageSpace}:`));n(o);return}if(t.data.method==="storage.remove"){this.assertPermissions(e,"storage",t),localStorage.removeItem(`${this.storageSpace}:${t.data.params.key}`),n(null);return}if(t.data.method==="panel.focus"){let o=this.activePanels[t.data.params.windowId];o&&o.focus(),n(null);return}if(t.data.method==="panel.postMessage"){let o=this.activePanels[t.data.params.windowId];o&&o.postMessage(t.data.params.data,"*"),n(null);return}if(t.data.method==="panel.close"){let o=this.activePanels[t.data.params.windowId];o&&o.close(),delete this.activePanels[t.data.params.windowId],n(null);return}if(t.data.method==="walletConnect.connect"){this.assertPermissions(e,"walletConnect",t);try{if(!this.connector.walletConnect)throw new Error("WalletConnect is not configured");let a=await(await this.connector.walletConnect).connect(t.data.params);a.approval(),n({uri:a.uri})}catch(o){r(o)}return}if(t.data.method==="walletConnect.getProjectId"){if(!this.connector.walletConnect)throw new Error("WalletConnect is not configured");this.assertPermissions(e,"walletConnect",t);let o=await this.connector.walletConnect;n(o.core.projectId);return}if(t.data.method==="walletConnect.disconnect"){this.assertPermissions(e,"walletConnect",t);try{if(!this.connector.walletConnect)throw new Error("WalletConnect is not configured");let a=await(await this.connector.walletConnect).disconnect(t.data.params);n(a)}catch(o){r(o)}return}if(t.data.method==="walletConnect.getSession"){this.assertPermissions(e,"walletConnect",t);try{if(!this.connector.walletConnect)throw new Error("WalletConnect is not configured");let o=await this.connector.walletConnect,a=o.session.keys[o.session.keys.length-1],i=a?o.session.get(a):null;n(i?{topic:i.topic,namespaces:i.namespaces}:null)}catch(o){r(o)}return}if(t.data.method==="walletConnect.request"){this.assertPermissions(e,"walletConnect",t);try{if(!this.connector.walletConnect)throw new Error("WalletConnect is not configured");let a=await(await this.connector.walletConnect).request(t.data.params);n(a)}catch(o){r(o)}return}if(t.data.method==="external"){this.assertPermissions(e,"external",t);try{let{entity:o,key:a,args:i}=t.data.params,l=o.split(".").reduce((w,Pe)=>w[Pe],window);o==="nightly.near"&&a==="signTransaction"&&(i[0].encode=()=>i[0]);let d=typeof l[a]=="function"?await l[a](...i||[]):l[a];n(d)}catch(o){r(o)}return}if(t.data.method==="open"){this.assertPermissions(e,"allowsOpen",t);let o=typeof window<"u"?window?.Telegram?.WebApp:null;if(o&&t.data.params.url.startsWith("https://t.me")){o.openTelegramLink(t.data.params.url);return}let a=window.open(t.data.params.url,"_blank",t.data.params.features),i=a?(0,Z.uuid4)():null,l=d=>{let w=(0,g.parseUrl)(t.data.params.url);w&&w.origin===d.origin&&e.postMessage(d.data)};if(n(i),window.addEventListener("message",l),a&&i){this.activePanels[i]=a;let d=setInterval(()=>{if(!a?.closed)return;window.removeEventListener("message",l);let w={method:"proxy-window:closed",windowId:i};delete this.activePanels[i],clearInterval(d);try{e.postMessage(w)}catch{}},500)}return}if(t.data.method==="open.nativeApp"){this.assertPermissions(e,"allowsOpen",t);let o=(0,g.parseUrl)(t.data.params.url);if(!o||["https","http","javascript:","file:","data:","blob:","about:"].includes(o.protocol))throw r("Invalid URL"),new Error("[open.nativeApp] Invalid URL");let i=document.createElement("iframe");i.src=t.data.params.url,i.style.display="none",document.body.appendChild(i),e.postMessage({...t.data,status:"success",result:null});return}};actualCode=null;async checkNewVersion(e,t){if(this.actualCode)return this.connector.logger?.log("New version of code already checked"),this.actualCode;let n=(0,g.parseUrl)(e.manifest.executor);if(n||(n=(0,g.parseUrl)(location.origin+e.manifest.executor)),!n)throw new Error("Invalid executor URL");n.searchParams.set("nonce",tt);let r=await fetch(n.toString()).then(o=>o.text());return this.connector.logger?.log("New version of code fetched"),this.actualCode=r,r===t?(this.connector.logger?.log("New version of code is the same as the current version"),this.actualCode):(await this.connector.db.setItem(`${this.manifest.id}:${this.manifest.version}`,r),this.connector.logger?.log("New version of code saved to cache"),r)}async loadCode(){let e=await this.connector.db.getItem(`${this.manifest.id}:${this.manifest.version}`).catch(()=>null);this.connector.logger?.log("Code loaded from cache",e!==null);let t=this.checkNewVersion(this,e);return e||await t}async call(e,t){this.connector.logger?.log("Add to queue",e,t),this.connector.logger?.log("Calling method",e,t);let n=await this.loadCode();this.connector.logger?.log("Code loaded, preparing");let r=new et.default(this,n,this._onMessage);this.connector.logger?.log("Code loaded, iframe initialized"),await r.readyPromise,this.connector.logger?.log("Iframe ready");let o=(0,Z.uuid4)();return new Promise((a,i)=>{try{let l=d=>{d.data.id!==o||d.data.origin!==r.origin||(r.dispose(),window.removeEventListener("message",l),this.connector.logger?.log("postMessage",{result:d.data,request:{method:e,params:t}}),d.data.status==="failed"?i(d.data.result):a(d.data.result))};window.addEventListener("message",l),r.postMessage({method:e,params:t,id:o}),r.on("close",()=>i(new Error("Wallet closed")))}catch(l){this.connector.logger?.log("Iframe error",l),i(l)}})}async getAllStorage(){let e=Object.keys(localStorage).filter(n=>n.startsWith(`${this.storageSpace}:`)),t={};for(let n of e)t[n.replace(`${this.storageSpace}:`,"")]=localStorage.getItem(n);return t}async clearStorage(){let e=Object.keys(localStorage).filter(t=>t.startsWith(`${this.storageSpace}:`));for(let t of e)localStorage.removeItem(t)}};b.default=ee});var ne=c(h=>{"use strict";var nt=h&&h.__importDefault||function(s){return s&&s.__esModule?s:{default:s}};Object.defineProperty(h,"__esModule",{value:!0});h.SandboxWallet=void 0;var te=p(),rt=nt(xe()),N=class{connector;manifest;executor;constructor(e,t){this.connector=e,this.manifest=t,this.executor=new rt.default(e,t)}async signIn(e){return this.executor.call("wallet:signIn",{network:e?.network??this.connector.network,addFunctionCallKey:e?.addFunctionCallKey})}async signInAndSignMessage(e){return this.executor.call("wallet:signInAndSignMessage",{network:e?.network??this.connector.network,addFunctionCallKey:e?.addFunctionCallKey,messageParams:e.messageParams})}async signOut(e){let t={...e,network:e?.network??this.connector.network};await this.executor.call("wallet:signOut",t),await this.executor.clearStorage()}async getAccounts(e){let t={...e,network:e?.network??this.connector.network};return this.executor.call("wallet:getAccounts",t)}async signAndSendTransaction(e){let t=(0,te.nearActionsToConnectorActions)(e.actions),n={...e,actions:t,network:e.network??this.connector.network};return this.executor.call("wallet:signAndSendTransaction",n)}async signAndSendTransactions(e){let t=e.transactions.map(r=>({actions:(0,te.nearActionsToConnectorActions)(r.actions),receiverId:r.receiverId})),n={...e,transactions:t,network:e.network??this.connector.network};return this.executor.call("wallet:signAndSendTransactions",n)}async signMessage(e){let t={...e,network:e.network??this.connector.network};return this.executor.call("wallet:signMessage",t)}async signDelegateActions(e){let t={...e,delegateActions:e.delegateActions.map(n=>({...n,actions:(0,te.nearActionsToConnectorActions)(n.actions)})),network:e.network??this.connector.network};return this.executor.call("wallet:signDelegateActions",t)}};h.SandboxWallet=N;h.default=N});var se=c(j=>{"use strict";Object.defineProperty(j,"__esModule",{value:!0});j.InjectedWallet=void 0;var re=p(),oe=class{connector;wallet;constructor(e,t){this.connector=e,this.wallet=t}get manifest(){return this.wallet.manifest}async signIn({addFunctionCallKey:e,network:t}){return this.wallet.signIn({network:t??this.connector.network,addFunctionCallKey:e})}async signInAndSignMessage(e){return this.wallet.signInAndSignMessage({network:e?.network??this.connector.network,addFunctionCallKey:e.addFunctionCallKey,messageParams:e.messageParams})}async signOut(e){await this.wallet.signOut({network:e?.network??this.connector.network})}async getAccounts(e){return this.wallet.getAccounts({network:e?.network??this.connector.network})}async signAndSendTransaction(e){let t=(0,re.nearActionsToConnectorActions)(e.actions),n=e.network??this.connector.network,r=await this.wallet.signAndSendTransaction({...e,actions:t,network:n});if(!r)throw new Error("No result from wallet");return Array.isArray(r.transactions)?r.transactions[0]:r}async signAndSendTransactions(e){let t=e.network??this.connector.network,n=e.transactions.map(o=>({actions:(0,re.nearActionsToConnectorActions)(o.actions),receiverId:o.receiverId})),r=await this.wallet.signAndSendTransactions({...e,transactions:n,network:t});if(!r)throw new Error("No result from wallet");return Array.isArray(r.transactions)?r.transactions:r}async signMessage(e){return this.wallet.signMessage({...e,network:e.network??this.connector.network})}async signDelegateActions(e){return this.wallet.signDelegateActions({...e,delegateActions:e.delegateActions.map(t=>({...t,actions:(0,re.nearActionsToConnectorActions)(t.actions)})),network:e.network??this.connector.network})}};j.InjectedWallet=oe});var ve=c(O=>{"use strict";Object.defineProperty(O,"__esModule",{value:!0});O.NearWalletsPopup=void 0;var f=_(),ot=R(),st=G(),at={id:"custom-wallet",name:"Custom Wallet",icon:"https://www.mynearwallet.com/images/webclip.png",description:"Custom wallet for NEAR.",website:"",version:"1.0.0",executor:"your-executor-url.js",type:"sandbox",platform:{},features:{signMessage:!0,signInWithoutAddKey:!0,signInAndSignMessage:!0,signAndSendTransaction:!0,signAndSendTransactions:!0,signDelegateActions:!0},permissions:{storage:!0,allowsOpen:[]}},ae=class extends st.Popup{delegate;constructor(e){super(e),this.delegate=e,this.update({wallets:e.wallets,showSettings:!1})}handlers(){super.handlers(),this.addListener(".settings-button","click",()=>this.update({showSettings:!0})),this.addListener(".back-button","click",()=>this.update({showSettings:!1})),this.root.querySelectorAll(".connect-item").forEach(e=>{e instanceof HTMLDivElement&&this.addListener(e,"click",()=>this.delegate.onSelect(e.dataset.type))}),this.root.querySelectorAll(".remove-wallet-button").forEach(e=>{e instanceof SVGSVGElement&&this.addListener(e,"click",async t=>{t.stopPropagation(),await this.delegate.onRemoveDebugManifest(e.dataset.type);let n=this.state.wallets.filter(r=>r.id!==e.dataset.type);this.update({wallets:n})})}),this.addListener(".add-debug-manifest-button","click",async()=>{try{let e=this.root.querySelector("#debug-manifest-input")?.value??"",t=await this.delegate.onAddDebugManifest(e);this.update({showSettings:!1,wallets:[t,...this.state.wallets]})}catch(e){alert(`Something went wrong: ${e}`)}})}create(){super.create({show:!0})}walletDom(e){let t=(0,f.html)`
      <svg
        class="remove-wallet-button"
        data-type="${e.id}"
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style="margin-right: 4px;"
      >
        <path d="M18 6L6 18" stroke="rgba(255,255,255,0.5)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M6 6L18 18" stroke="rgba(255,255,255,0.5)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    `;return(0,f.html)`
      <div class="connect-item" data-type="${e.id}">
        <img style="background: #333" src="${e.icon}" alt="${e.name}" />
        <div class="connect-item-info">
          <span>${e.name}</span>
          <span class="wallet-address">${(0,ot.parseUrl)(e.website)?.hostname}</span>
        </div>
        ${e.debug?t:""}
      </div>
    `}get footer(){if(!this.delegate.footer)return"";let{icon:e,heading:t,link:n,linkText:r}=this.delegate.footer;return(0,f.html)`
      <div class="footer">
        ${e?(0,f.html)`<img src="${e}" alt="${t}" />`:""}
        <p>${t}</p>
        <a class="get-wallet-link" href="${n}" target="_blank">${r}</a>
      </div>
    `}get dom(){return this.state.showSettings?(0,f.html)`
        <div class="modal-container">
          <div class="modal-content">
            <div class="modal-header">
              <button class="back-button" style="left: 16px; right: unset;">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M15 18L9 12L15 6" stroke="rgba(255,255,255,0.5)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>
              <p>Settings</p>
            </div>

            <div class="modal-body">
              <p style="text-align: left;">
                You can add your wallet to dapp for debug,
                <a href="https://github.com/azbang/hot-connector" target="_blank">read the documentation.</a> Paste your manifest and click "Add".
              </p>

              <textarea style="width: 100%;" id="debug-manifest-input" rows="10">${JSON.stringify(at,null,2)}</textarea>
              <button class="add-debug-manifest-button">Add</button>
            </div>

            ${this.footer}
          </div>
        </div>
      `:(0,f.html)`<div class="modal-container">
      <div class="modal-content">
        <div class="modal-header">
          <p>Select wallet</p>
          <button class="settings-button">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="2" fill="rgba(255,255,255,0.5)" />
              <circle cx="19" cy="12" r="2" fill="rgba(255,255,255,0.5)" />
              <circle cx="5" cy="12" r="2" fill="rgba(255,255,255,0.5)" />
            </svg>
          </button>
        </div>

        <div class="modal-body">${this.state.wallets.map(e=>this.walletDom(e))}</div>

        ${this.footer}
      </div>
    </div>`}};O.NearWalletsPopup=ae});var ke=c(le=>{"use strict";Object.defineProperty(le,"__esModule",{value:!0});var ie=class{dbName;storeName;version;constructor(e,t){this.dbName=e,this.storeName=t,this.version=1}getDb(){return new Promise((e,t)=>{if(typeof window>"u"||typeof indexedDB>"u"){t(new Error("IndexedDB is not available (SSR environment)"));return}let n=indexedDB.open(this.dbName,this.version);n.onerror=r=>{console.error("Error opening database:",r.target.error),t(new Error("Error opening database"))},n.onsuccess=r=>{e(n.result)},n.onupgradeneeded=r=>{let o=n.result;o.objectStoreNames.contains(this.storeName)||o.createObjectStore(this.storeName)}})}async getItem(e){let t=await this.getDb();if(typeof e=="number"&&(e=e.toString()),typeof e!="string")throw new Error("Key must be a string");return new Promise((n,r)=>{if(!this.storeName){r(new Error("Store name not set"));return}let o=t.transaction(this.storeName,"readonly");o.onerror=l=>r(o.error);let i=o.objectStore(this.storeName).get(e);i.onerror=l=>r(i.error),i.onsuccess=()=>{n(i.result),t.close()}})}async setItem(e,t){let n=await this.getDb();if(typeof e=="number"&&(e=e.toString()),typeof e!="string")throw new Error("Key must be a string");return new Promise((r,o)=>{if(!this.storeName){o(new Error("Store name not set"));return}let a=n.transaction(this.storeName,"readwrite");a.onerror=d=>o(a.error);let l=a.objectStore(this.storeName).put(t,e);l.onerror=d=>o(l.error),l.onsuccess=()=>{n.close(),r()}})}async removeItem(e){let t=await this.getDb();if(typeof e=="number"&&(e=e.toString()),typeof e!="string")throw new Error("Key must be a string");return new Promise((n,r)=>{if(!this.storeName){r(new Error("Store name not set"));return}let o=t.transaction(this.storeName,"readwrite");o.onerror=l=>r(o.error);let i=o.objectStore(this.storeName).delete(e);i.onerror=l=>r(i.error),i.onsuccess=()=>{t.close(),n()}})}async keys(){let e=await this.getDb();return new Promise((t,n)=>{if(!this.storeName){n(new Error("Store name not set"));return}let r=e.transaction(this.storeName,"readonly");r.onerror=i=>n(r.error);let a=r.objectStore(this.storeName).getAllKeys();a.onerror=i=>n(a.error),a.onsuccess=()=>{t(a.result),e.close()}})}async count(){let e=await this.getDb();return new Promise((t,n)=>{if(!this.storeName){n(new Error("Store name not set"));return}let r=e.transaction(this.storeName,"readonly");r.onerror=i=>n(r.error);let a=r.objectStore(this.storeName).count();a.onerror=i=>n(a.error),a.onsuccess=()=>{t(a.result),e.close()}})}async length(){return this.count()}async clear(){let e=await this.getDb();return new Promise((t,n)=>{if(!this.storeName){n(new Error("Store name not set"));return}let r=e.transaction(this.storeName,"readwrite");r.onerror=i=>n(r.error);let a=r.objectStore(this.storeName).clear();a.onerror=i=>n(a.error),a.onsuccess=()=>{e.close(),t()}})}};le.default=ie});var Se=c(m=>{"use strict";var it=m&&m.__importDefault||function(s){return s&&s.__esModule?s:{default:s}};Object.defineProperty(m,"__esModule",{value:!0});m.NearConnector=void 0;var lt=B(),ct=ve(),dt=D(),ut=it(ke()),ht=U(),wt=se(),Ce=ne(),gt=["https://raw.githubusercontent.com/hot-dao/near-selector/refs/heads/main/repository/manifest.json","https://cdn.jsdelivr.net/gh/azbang/hot-connector/repository/manifest.json"];function ft(s){return e=>Object.entries(s).length===0?!0:Object.entries(s).filter(([t,n])=>n===!0).every(([t])=>e.manifest.features?.[t]===!0)}var ce=class{storage;events;db;logger;wallets=[];manifest={wallets:[],version:"1.0.0"};features={};network="mainnet";providers={mainnet:[],testnet:[]};walletConnect;footerBranding;excludedWallets=[];autoConnect;whenManifestLoaded;constructor(e){this.db=new ut.default("hot-connector","wallets"),this.storage=e?.storage??new dt.LocalStorage,this.events=e?.events??new lt.EventEmitter,this.logger=e?.logger,this.network=e?.network??"mainnet",this.walletConnect=e?.walletConnect,this.autoConnect=e?.autoConnect??!0,this.providers=e?.providers??{mainnet:[],testnet:[]},this.excludedWallets=e?.excludedWallets??[],this.features=e?.features??{},e?.footerBranding!==void 0?this.footerBranding=e?.footerBranding:this.footerBranding={icon:"data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%20512%20512%22%20class%3D%22size-7%22%3E%3Crect%20width%3D%22512%22%20height%3D%22512%22%20fill%3D%22%2300ec97%22%20rx%3D%22110%22%2F%3E%3Cpath%20fill%3D%22%23000%22%20d%3D%22M373.89%20106.199a31.95%2031.95%200%200%200-27.213%2015.207l-62.631%2092.979a6.67%206.67%200%200%200-.989%205.001%206.66%206.66%200%200%200%202.837%204.235%206.67%206.67%200%200%200%208.032-.494l61.643-53.47c1.02-.924%202.599-.827%203.523.193.419.473.644%201.074.644%201.697v167.402a2.49%202.49%200%200%201-2.502%202.491%202.48%202.48%200%200%201-1.912-.891L168.976%20117.497a31.93%2031.93%200%200%200-24.356-11.298h-6.508c-17.623%200-31.917%2014.294-31.917%2031.917v235.767c0%2017.623%2014.294%2031.917%2031.917%2031.917a31.94%2031.94%200%200%200%2027.213-15.206l62.631-92.98a6.66%206.66%200%200%200-1.847-9.236%206.67%206.67%200%200%200-8.033.494l-61.643%2053.471c-1.02.923-2.599.826-3.522-.194a2.5%202.5%200%200%201-.634-1.697V173.008a2.49%202.49%200%200%201%202.502-2.492c.731%200%201.439.322%201.912.891l186.313%20223.096a31.95%2031.95%200%200%200%2024.357%2011.297h6.508c17.623%200%2031.927-14.272%2031.938-31.895V138.116c0-17.623-14.294-31.917-31.917-31.917%22%2F%3E%3C%2Fsvg%3E",heading:"NEAR Connector",link:"https://wallet.near.org",linkText:"Don't have a wallet?"},this.whenManifestLoaded=new Promise(async t=>{e?.manifest==null||typeof e.manifest=="string"?this.manifest=await this._loadManifest(e?.manifest).catch(()=>({wallets:[],version:"1.0.0"})):this.manifest=e?.manifest??{wallets:[],version:"1.0.0"};let n=new Set(this.excludedWallets);n.delete("hot-wallet"),this.manifest.wallets=this.manifest.wallets.filter(r=>!(r.permissions.walletConnect&&!this.walletConnect||n.has(r.id))),await new Promise(r=>setTimeout(r,100)),t()}),typeof window<"u"&&(window.addEventListener("near-wallet-injected",this._handleNearWalletInjected),window.dispatchEvent(new Event("near-selector-ready")),window.addEventListener("message",async t=>{t.data.type==="near-wallet-injected"&&(await this.whenManifestLoaded.catch(()=>{}),this.wallets=this.wallets.filter(n=>n.manifest.id!==t.data.manifest.id),this.wallets.unshift(new ht.ParentFrameWallet(this,t.data.manifest)),this.events.emit("selector:walletsChanged",{}),this.autoConnect&&this.connect({walletId:t.data.manifest.id}))})),this.whenManifestLoaded.then(()=>{typeof window<"u"&&window.parent.postMessage({type:"near-selector-ready"},"*"),this.manifest.wallets.forEach(t=>this.registerWallet(t)),this.storage.get("debug-wallets").then(t=>{JSON.parse(t??"[]").forEach(r=>this.registerDebugWallet(r))})})}get availableWallets(){return this.wallets.filter(t=>Object.entries(this.features).every(([n,r])=>!(r&&!t.manifest.features?.[n]))).filter(t=>!(this.network==="testnet"&&!t.manifest.features?.testnet))}_handleNearWalletInjected=e=>{this.wallets=this.wallets.filter(t=>t.manifest.id!==e.detail.manifest.id),this.wallets.unshift(new wt.InjectedWallet(this,e.detail)),this.events.emit("selector:walletsChanged",{})};async _loadManifest(e){let t=e?[e]:gt;for(let n of t){let r=await fetch(n).catch(()=>null);if(!(!r||!r.ok))return await r.json()}throw new Error("Failed to load manifest")}async switchNetwork(e,t){this.network!==e&&(await this.disconnect().catch(()=>{}),this.network=e,await this.connect(t))}async registerWallet(e){if(e.type!=="sandbox")throw new Error("Only sandbox wallets are supported");this.wallets.find(t=>t.manifest.id===e.id)||(this.wallets.push(new Ce.SandboxWallet(this,e)),this.events.emit("selector:walletsChanged",{}))}async registerDebugWallet(e){let t=typeof e=="string"?JSON.parse(e):e;if(t.type!=="sandbox")throw new Error("Only sandbox wallets type are supported");if(!t.id)throw new Error("Manifest must have an id");if(!t.name)throw new Error("Manifest must have a name");if(!t.icon)throw new Error("Manifest must have an icon");if(!t.website)throw new Error("Manifest must have a website");if(!t.version)throw new Error("Manifest must have a version");if(!t.executor)throw new Error("Manifest must have an executor");if(!t.features)throw new Error("Manifest must have features");if(!t.permissions)throw new Error("Manifest must have permissions");if(this.wallets.find(r=>r.manifest.id===t.id))throw new Error("Wallet already registered");t.debug=!0,this.wallets.unshift(new Ce.SandboxWallet(this,t)),this.events.emit("selector:walletsChanged",{});let n=this.wallets.filter(r=>r.manifest.debug).map(r=>r.manifest);return this.storage.set("debug-wallets",JSON.stringify(n)),t}async removeDebugWallet(e){this.wallets=this.wallets.filter(n=>n.manifest.id!==e);let t=this.wallets.filter(n=>n.manifest.debug).map(n=>n.manifest);this.storage.set("debug-wallets",JSON.stringify(t)),this.events.emit("selector:walletsChanged",{})}async selectWallet({features:e={}}={}){return await this.whenManifestLoaded.catch(()=>{}),new Promise((t,n)=>{let r=new ct.NearWalletsPopup({footer:this.footerBranding,wallets:this.availableWallets.filter(ft(e)).map(o=>o.manifest),onRemoveDebugManifest:async o=>this.removeDebugWallet(o),onAddDebugManifest:async o=>this.registerDebugWallet(o),onReject:()=>(n(new Error("User rejected")),r.destroy()),onSelect:o=>(t(o),r.destroy())});r.create()})}async connect(e={}){let t=e.walletId,n=e.signMessageParams;await this.whenManifestLoaded.catch(()=>{}),t||(t=await this.selectWallet({features:{signInAndSignMessage:e.signMessageParams!=null?!0:void 0,signInWithFunctionCallKey:e.addFunctionCallKey!=null?!0:void 0}}));try{let r=await this.wallet(t);this.logger?.log("Wallet available to connect",r),await this.storage.set("selected-wallet",t),this.logger?.log(`Set preferred wallet, try to signIn${n!=null?" (with signed message)":""}`,t);let o;if(e.addFunctionCallKey!=null&&(this.logger?.log("Adding function call access key during sign in with params",e.addFunctionCallKey),o={...e.addFunctionCallKey,gasAllowance:e.addFunctionCallKey.gasAllowance??{amount:"250000000000000000000000",kind:"limited"}}),n!=null){let a=await r.signInAndSignMessage({addFunctionCallKey:o,messageParams:n,network:this.network});if(!a?.length)throw new Error("Failed to sign in");this.logger?.log("Signed in to wallet (with signed message)",t,a),this.events.emit("wallet:signInAndSignMessage",{wallet:r,accounts:a,success:!0}),this.events.emit("wallet:signIn",{wallet:r,accounts:a.map(i=>({accountId:i.accountId,publicKey:i.publicKey})),success:!0,source:"signInAndSignMessage"})}else{let a=await r.signIn({addFunctionCallKey:o,network:this.network});if(!a?.length)throw new Error("Failed to sign in");this.logger?.log("Signed in to wallet",t,a),this.events.emit("wallet:signIn",{wallet:r,accounts:a,success:!0,source:"signIn"})}return r}catch(r){throw this.logger?.log("Failed to connect to wallet",r),r}}async disconnect(e){e||(e=await this.wallet()),await e.signOut({network:this.network}),await this.storage.remove("selected-wallet"),this.events.emit("wallet:signOut",{success:!0})}async getConnectedWallet(){await this.whenManifestLoaded.catch(()=>{});let e=await this.storage.get("selected-wallet"),t=this.wallets.find(r=>r.manifest.id===e);if(!t)throw new Error("No wallet selected");let n=await t.getAccounts();if(!n?.length)throw new Error("No accounts found");return{wallet:t,accounts:n}}async wallet(e){if(await this.whenManifestLoaded.catch(()=>{}),!e)return this.getConnectedWallet().then(({wallet:n})=>n).catch(async()=>{throw await this.storage.remove("selected-wallet"),new Error("No accounts found")});let t=this.wallets.find(n=>n.manifest.id===e);if(!t)throw new Error("Wallet not found");return t}async use(e){await this.whenManifestLoaded.catch(()=>{}),this.wallets=this.wallets.map(t=>new Proxy(t,{get(n,r,o){let a=Reflect.get(n,r,o);if(r in e&&typeof a=="function"){let i=e[r];return function(...l){let d=()=>a.apply(n,l);return l.length>0?i.call(this,...l,d):i.call(this,void 0,d)}}return a}}))}on(e,t){this.events.on(e,t)}once(e,t){this.events.once(e,t)}off(e,t){this.events.off(e,t)}removeAllListeners(e){this.events.removeAllListeners(e)}};m.NearConnector=ce});var Ae=c(u=>{"use strict";Object.defineProperty(u,"__esModule",{value:!0});u.nearActionsToConnectorActions=u.NearConnector=u.InjectedWallet=u.SandboxWallet=u.ParentFrameWallet=u.LocalStorage=void 0;var mt=D();Object.defineProperty(u,"LocalStorage",{enumerable:!0,get:function(){return mt.LocalStorage}});var pt=U();Object.defineProperty(u,"ParentFrameWallet",{enumerable:!0,get:function(){return pt.ParentFrameWallet}});var yt=ne();Object.defineProperty(u,"SandboxWallet",{enumerable:!0,get:function(){return yt.SandboxWallet}});var bt=se();Object.defineProperty(u,"InjectedWallet",{enumerable:!0,get:function(){return bt.InjectedWallet}});var xt=Se();Object.defineProperty(u,"NearConnector",{enumerable:!0,get:function(){return xt.NearConnector}});var vt=p();Object.defineProperty(u,"nearActionsToConnectorActions",{enumerable:!0,get:function(){return vt.nearActionsToConnectorActions}})});var q=Ne(Ae()),{__esModule:zt,nearActionsToConnectorActions:Bt,NearConnector:Ht,InjectedWallet:Vt,SandboxWallet:Gt,ParentFrameWallet:Jt,LocalStorage:Yt}=q,Xt=q.default??q;export{Vt as InjectedWallet,Yt as LocalStorage,Ht as NearConnector,Jt as ParentFrameWallet,Gt as SandboxWallet,zt as __esModule,Xt as default,Bt as nearActionsToConnectorActions};
//# sourceMappingURL=near-connect.bundle.mjs.map