function setup() {
createCanvas(400,400)
}

function draw() {
  background(255,255,254);
  noStroke()
  fill("blue")
  circle(mouseX,mouseY,50)
  triangle(mouseX+20, mouseY-15, mouseX, mouseY-35, mouseX-20,mouseY-15)
}