export function cameraDistance(radius, verticalFov, aspect) {
  const v = verticalFov * Math.PI / 360;
  const h = Math.atan(Math.tan(v) * Math.max(aspect, .01));
  return radius / Math.sin(Math.min(v, h)) * 1.10;
}
export function decay(envelope, seconds, rate = 3.4) {
  return envelope * Math.exp(-rate * Math.max(0, seconds));
}
export const profiles = {
  IDLE: [.16, .28, .44], LISTENING: [.52, .65, .76], THINKING: [.68, 1.1, .74],
  EXECUTING: [.86, 1.45, .94], SPEAKING: [.72, .85, 1], INTERRUPTED: [.32, .35, .52],
  WAITING_FOR_USER: [.24, .30, .54], ERROR: [.18, .18, .37]
};
