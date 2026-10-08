import * as THREE from './vendor/three.module.js';
import {cameraDistance, decay, profiles} from './motion.mjs';

export class Orb {
  constructor(container) {
    this.container = container;
    this.state = 'IDLE'; this.envelope = 0; this.current = [...profiles.IDLE];
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, .1, 100);
    this.renderer = new THREE.WebGLRenderer({alpha:true, antialias:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    container.appendChild(this.renderer.domElement);
    this.group = new THREE.Group(); this.scene.add(this.group);
    this.uniforms = {uTime:{value:0}, uEnergy:{value:.2}, uGlow:{value:.4}};
    const material = new THREE.ShaderMaterial({uniforms:this.uniforms, transparent:true, depthWrite:false,
      blending:THREE.AdditiveBlending, side:THREE.DoubleSide,
      vertexShader:`uniform float uTime; uniform float uEnergy; varying vec3 vNormal; varying vec3 vPosition; varying float vNoise;
      float hash(vec3 p){return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453);}
      float noise(vec3 p){vec3 i=floor(p),f=fract(p); f=f*f*(3.0-2.0*f);
        return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
        mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);}
      void main(){float n=clamp((noise(normal*3.6+uTime*.19)*.7+noise(normal*7.2-uTime*.11)*.3)*2.0-1.0,-1.0,1.0);
        vec3 p=position+normal*(.16*clamp(uEnergy,0.0,1.0)*n);
        vNormal=normalize(normalMatrix*normal);vPosition=(modelViewMatrix*vec4(p,1.0)).xyz;vNoise=n;
        gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);}`,
      fragmentShader:`uniform float uTime;uniform float uGlow;varying vec3 vNormal;varying vec3 vPosition;varying float vNoise;
      void main(){float rim=pow(1.0-abs(dot(normalize(vNormal),normalize(-vPosition))),2.5);
        float bands=pow(.5+.5*sin(vPosition.y*34.0+vNoise*9.0-uTime*.5),14.0);
        vec3 color=mix(vec3(.72,.015,.06),vec3(1.0,.19,.30),rim);
        gl_FragColor=vec4(color,(rim*.75+bands*.17+.035)*(uGlow+.3));}`});
    this.shell = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 5), material); this.group.add(this.shell);
    this.core = new THREE.Mesh(new THREE.IcosahedronGeometry(.65, 4), new THREE.ShaderMaterial({
      uniforms:this.uniforms,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,
      vertexShader:`varying vec3 n;varying vec3 p;void main(){n=normalize(normalMatrix*normal);p=(modelViewMatrix*vec4(position,1.)).xyz;gl_Position=projectionMatrix*vec4(p,1.);}`,
      fragmentShader:`varying vec3 n;varying vec3 p;uniform float uGlow;void main(){float a=pow(abs(dot(normalize(n),normalize(-p))),2.0);gl_FragColor=vec4(1.,.045,.11,a*(.30+uGlow*.36));}`
    })); this.group.add(this.core);
    this.cage = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.IcosahedronGeometry(1.25, 2)),
      new THREE.LineBasicMaterial({color:0xfb3859,transparent:true,opacity:.22,blending:THREE.AdditiveBlending}));this.group.add(this.cage);
    const wire = new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.IcosahedronGeometry(1.025, 3)),
      new THREE.LineBasicMaterial({color:0xfe244e,transparent:true,opacity:.20}));this.group.add(wire);
    const positions=[];
    for(let i=0;i<180;i++){const y=1-2*i/179;const r=Math.sqrt(1-y*y);const a=i*2.399963;positions.push(1.31*r*Math.cos(a),1.31*y,1.31*r*Math.sin(a));}
    const points=new THREE.BufferGeometry();points.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
    this.particles=new THREE.Points(points,new THREE.PointsMaterial({color:0xff8297,size:.018,transparent:true,opacity:.75}));this.group.add(this.particles);
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    new ResizeObserver(()=>this.resize()).observe(container);this.resize();
    this.last=performance.now();this.phase=0;this.animate=this.animate.bind(this);requestAnimationFrame(this.animate);
  }
  resize(){const w=this.container.clientWidth,h=this.container.clientHeight;if(!w||!h)return;this.renderer.setSize(w,h);this.camera.aspect=w/h;this.camera.position.z=cameraDistance(1.40,38,w/h);this.camera.updateProjectionMatrix();}
  setState(state){if(state===this.state)return;if(state==='SPEAKING')this.envelope=1;this.state=state;this.holdUntil=performance.now()+(state==='IDLE'?320:0);}
  animate(now){requestAnimationFrame(this.animate);const dt=Math.max(0,(now-this.last)/1000);this.last=now;this.envelope=decay(this.envelope,dt);
    const target=this.state==='IDLE'&&now<this.holdUntil?profiles.WAITING_FOR_USER:profiles[this.state]||profiles.IDLE;const smooth=1-Math.exp(-3*dt);for(let i=0;i<3;i++)this.current[i]+=(target[i]-this.current[i])*smooth;
    this.phase+=dt*this.current[1]*(this.reduced?.15:1);this.uniforms.uTime.value=this.phase;
    this.uniforms.uEnergy.value=Math.min(1,this.current[0]+this.envelope*.25);this.uniforms.uGlow.value=this.current[2]+this.envelope*.25;
    const scale=1+Math.sin(this.phase*1.8)*.018+this.envelope*.025;this.group.scale.setScalar(scale);
    this.cage.rotation.set(this.phase*.13,this.phase*.17,.2);this.particles.rotation.y=-this.phase*.09;this.shell.rotation.y=this.phase*.045;
    this.core.scale.setScalar(1+Math.sin(this.phase*2)*.045);this.renderer.render(this.scene,this.camera);
  }
}
