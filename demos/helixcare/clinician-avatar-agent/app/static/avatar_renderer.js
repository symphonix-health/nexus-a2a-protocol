window.AvatarRenderer = (() => {
  let scene;
  let camera;
  let renderer;
  let head;

  const skinTones = {
    male_black: 0x7a4f32,
    male_white: 0xd8b59b,
    female_black: 0x6b442a,
    female_white: 0xe3c4aa,
  };

  function init(containerId) {
    const container = document.getElementById(containerId);
    const width = container.clientWidth;
    const height = container.clientHeight;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x050b16);

    camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.set(0, 1.2, 3.1);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const light = new THREE.DirectionalLight(0xffffff, 1.2);
    light.position.set(2, 4, 3);
    scene.add(light);
    scene.add(new THREE.AmbientLight(0x88aacc, 0.35));

    const neckGeo = new THREE.CylinderGeometry(0.25, 0.28, 0.4, 16);
    const neckMat = new THREE.MeshStandardMaterial({ color: 0xb58e72 });
    const neck = new THREE.Mesh(neckGeo, neckMat);
    neck.position.y = 0.3;
    scene.add(neck);

    const geo = new THREE.SphereGeometry(0.72, 32, 32);
    const mat = new THREE.MeshStandardMaterial({ color: 0xd8b59b });
    head = new THREE.Mesh(geo, mat);
    head.position.y = 1.0;
    scene.add(head);

    const mouthGeo = new THREE.BoxGeometry(0.35, 0.08, 0.05);
    const mouthMat = new THREE.MeshStandardMaterial({ color: 0x552222 });
    const mouth = new THREE.Mesh(mouthGeo, mouthMat);
    mouth.position.set(0, 0.85, 0.67);
    mouth.name = "mouth";
    scene.add(mouth);

    animate();
  }

  function setAvatar(avatarKey) {
    if (!head) return;
    const tone = skinTones[avatarKey] || 0xd8b59b;
    head.material.color.setHex(tone);
  }

  function applyViseme(weight = 0) {
    const mouth = scene.getObjectByName("mouth");
    if (!mouth) return;
    mouth.scale.y = 1 + Math.max(0, Math.min(1, weight)) * 2.2;
  }

  function animate() {
    requestAnimationFrame(animate);
    if (head) {
      head.rotation.y = Math.sin(Date.now() / 1800) * 0.08;
    }
    renderer.render(scene, camera);
  }

  return { init, setAvatar, applyViseme };
})();
