--!nonstrict
-- ============================================================
-- MUNDO FÉNIX · R1.1 — Casa del Árbol + el loop del verbo
-- ============================================================
-- Prueba el corazón del diseño (SPEC-MUNDO-SOCIAL-ROBLOX.md §1b):
--   RECLAMAR → DECIDIR → GASTAR → VER EVOLUCIONAR
-- Todo LOCAL y con Plata SIMULADA (mock). NO toca Railway ni producción.
-- Objetivo: sentir el loop en Studio antes de conectar las monedas reales (R1.2).
--
-- CÓMO USARLO (Roblox Studio):
--   1. Nueva experiencia con plantilla "Baseplate".
--   2. En el panel Explorer: StarterPlayer → StarterPlayerScripts.
--   3. Click derecho sobre StarterPlayerScripts → Insert Object → LocalScript.
--   4. Borrá el contenido del LocalScript y pegá TODO este archivo.
--   5. Apretá Play (▶). Aparece tu Casa del Árbol + los botones.
--   6. Reclamá Plata, subí de nivel y mirá cómo la Casa evoluciona.
-- ============================================================

local Players = game:GetService("Players")
local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

-- ---------- Estado del juego (mock; en R1.2 vendrá de Railway) ----------
local plata = 0
local nivelCasa = 1
local NIVEL_MAX = 10
local RECLAMO = 50            -- cada "Reclamar" simula Plata ganada entrenando

-- costo de subir de nivel (escala con el nivel → la escasez es el motor)
local function costoSubir(n)
	return n * 100
end

-- ============================================================
-- LA CASA DEL ÁRBOL — se reconstruye entera en cada nivel
-- (evoluciona sola por nivel; el niño NO la edita, SPEC §4.1)
-- ============================================================
local BASE = Vector3.new(0, 0, -15)   -- unos pasos delante del spawn

local function construirCasa()
	local viejo = workspace:FindFirstChild("CasaDelArbol")
	if viejo then viejo:Destroy() end

	local modelo = Instance.new("Model")
	modelo.Name = "CasaDelArbol"

	local t = (nivelCasa - 1) / (NIVEL_MAX - 1)   -- 0 en nivel 1, 1 en nivel 10

	-- tronco (crece un poco con el nivel)
	local alturaTronco = 6 + nivelCasa * 0.5
	local tronco = Instance.new("Part")
	tronco.Name = "Tronco"
	tronco.Size = Vector3.new(3, alturaTronco, 3)
	tronco.Position = BASE + Vector3.new(0, alturaTronco / 2, 0)
	tronco.Anchored = true
	tronco.Color = Color3.fromRGB(102, 63, 30)
	tronco.Material = Enum.Material.Wood
	tronco.Parent = modelo

	-- cabaña (crece y cambia de color: madera → dorada en niveles altos)
	local lado = 5 + nivelCasa
	local altura = 4 + nivelCasa * 0.4
	local cabana = Instance.new("Part")
	cabana.Name = "Cabana"
	cabana.Size = Vector3.new(lado, altura, lado)
	cabana.Position = BASE + Vector3.new(0, alturaTronco + altura / 2, 0)
	cabana.Anchored = true
	cabana.Color = Color3.fromRGB(200, 180 + math.floor(20 * t), 120 + math.floor(110 * t))
	cabana.Material = Enum.Material.WoodPlanks
	cabana.Parent = modelo

	-- techo
	local techo = Instance.new("Part")
	techo.Name = "Techo"
	techo.Size = Vector3.new(lado + 1.5, 1.5, lado + 1.5)
	techo.Position = BASE + Vector3.new(0, alturaTronco + altura + 0.75, 0)
	techo.Anchored = true
	techo.Color = Color3.fromRGB(150, 40, 40)
	techo.Material = Enum.Material.Slate
	techo.Parent = modelo

	-- banderas doradas = tu nivel actual (progreso visible de un vistazo)
	for i = 1, nivelCasa do
		local ang = (i / nivelCasa) * math.pi * 2
		local bandera = Instance.new("Part")
		bandera.Name = "Bandera" .. i
		bandera.Size = Vector3.new(0.3, 2.2, 0.3)
		bandera.Position = BASE + Vector3.new(
			math.cos(ang) * (lado / 2),
			alturaTronco + altura + 2.2,
			math.sin(ang) * (lado / 2)
		)
		bandera.Anchored = true
		bandera.Color = Color3.fromRGB(255, 200, 40)
		bandera.Material = Enum.Material.Neon
		bandera.Parent = modelo
	end

	-- cartel con el nivel, flotando sobre la casa
	local cartel = Instance.new("Part")
	cartel.Name = "Cartel"
	cartel.Size = Vector3.new(6, 1.5, 0.2)
	cartel.Position = BASE + Vector3.new(0, alturaTronco + altura + 5, 0)
	cartel.Anchored = true
	cartel.Transparency = 1
	cartel.Parent = modelo

	local gui = Instance.new("BillboardGui")
	gui.Size = UDim2.new(0, 200, 0, 50)
	gui.AlwaysOnTop = true
	gui.Parent = cartel
	local txt = Instance.new("TextLabel")
	txt.Size = UDim2.new(1, 0, 1, 0)
	txt.BackgroundTransparency = 1
	txt.Text = "🌳 Casa nivel " .. nivelCasa
	txt.TextColor3 = Color3.fromRGB(255, 220, 120)
	txt.TextScaled = true
	txt.Font = Enum.Font.FredokaOne
	txt.Parent = gui

	modelo.Parent = workspace
end

-- ============================================================
-- INTERFAZ — panel de estado + botones (reclamar / subir)
-- ============================================================
local screen = Instance.new("ScreenGui")
screen.Name = "MundoFenixR1"
screen.ResetOnSpawn = false
screen.Parent = playerGui

local function esquinaRedondeada(obj, radio)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radio or 12)
	c.Parent = obj
end

-- panel superior
local panel = Instance.new("Frame")
panel.Size = UDim2.new(0, 340, 0, 74)
panel.Position = UDim2.new(0, 20, 0, 20)
panel.BackgroundColor3 = Color3.fromRGB(15, 20, 40)
panel.BackgroundTransparency = 0.1
panel.Parent = screen
esquinaRedondeada(panel, 16)

local lblPlata = Instance.new("TextLabel")
lblPlata.Size = UDim2.new(1, -20, 0, 34)
lblPlata.Position = UDim2.new(0, 14, 0, 6)
lblPlata.BackgroundTransparency = 1
lblPlata.TextXAlignment = Enum.TextXAlignment.Left
lblPlata.Font = Enum.Font.FredokaOne
lblPlata.TextScaled = true
lblPlata.TextColor3 = Color3.fromRGB(230, 230, 240)
lblPlata.Parent = panel

local lblNivel = Instance.new("TextLabel")
lblNivel.Size = UDim2.new(1, -20, 0, 26)
lblNivel.Position = UDim2.new(0, 14, 0, 42)
lblNivel.BackgroundTransparency = 1
lblNivel.TextXAlignment = Enum.TextXAlignment.Left
lblNivel.Font = Enum.Font.Gotham
lblNivel.TextScaled = true
lblNivel.TextColor3 = Color3.fromRGB(150, 200, 255)
lblNivel.Parent = panel

-- botón genérico
local function crearBoton(texto, y, color)
	local b = Instance.new("TextButton")
	b.Size = UDim2.new(0, 340, 0, 56)
	b.Position = UDim2.new(0, 20, 0, y)
	b.BackgroundColor3 = color
	b.Text = texto
	b.Font = Enum.Font.FredokaOne
	b.TextScaled = true
	b.TextColor3 = Color3.fromRGB(20, 20, 20)
	b.AutoButtonColor = true
	b.Parent = screen
	esquinaRedondeada(b, 14)
	-- padding de texto
	local pad = Instance.new("UIPadding")
	pad.PaddingLeft = UDim.new(0, 16)
	pad.PaddingRight = UDim.new(0, 16)
	pad.Parent = b
	return b
end

local btnReclamar = crearBoton("", 110, Color3.fromRGB(74, 222, 128))
local btnSubir = crearBoton("", 178, Color3.fromRGB(255, 183, 3))

-- mensaje flotante (feedback)
local lblMsg = Instance.new("TextLabel")
lblMsg.Size = UDim2.new(0, 340, 0, 30)
lblMsg.Position = UDim2.new(0, 20, 0, 244)
lblMsg.BackgroundTransparency = 1
lblMsg.Font = Enum.Font.GothamBold
lblMsg.TextScaled = true
lblMsg.TextColor3 = Color3.fromRGB(252, 165, 165)
lblMsg.Text = ""
lblMsg.Parent = screen

local function actualizarUI()
	lblPlata.Text = "🥈 Plata: " .. plata
	lblNivel.Text = "🏠 Casa nivel " .. nivelCasa .. " / " .. NIVEL_MAX
	btnReclamar.Text = "✋ Reclamar (+" .. RECLAMO .. ")"
	if nivelCasa >= NIVEL_MAX then
		btnSubir.Text = "🏠 ¡Casa al máximo!"
	else
		btnSubir.Text = "🏠 Subir de nivel  (cuesta " .. costoSubir(nivelCasa) .. ")"
	end
end

-- ---------- Acciones del loop ----------
btnReclamar.MouseButton1Click:Connect(function()
	-- R1.1: simula lo ganado entrenando. En R1.2 esto lo trae Railway.
	plata = plata + RECLAMO
	lblMsg.TextColor3 = Color3.fromRGB(134, 239, 172)
	lblMsg.Text = "¡Cosechaste tu esfuerzo! +" .. RECLAMO
	actualizarUI()
end)

btnSubir.MouseButton1Click:Connect(function()
	if nivelCasa >= NIVEL_MAX then
		lblMsg.TextColor3 = Color3.fromRGB(252, 211, 77)
		lblMsg.Text = "Tu Casa ya es legendaria ✨"
		return
	end
	local costo = costoSubir(nivelCasa)
	if plata < costo then
		lblMsg.TextColor3 = Color3.fromRGB(252, 165, 165)
		lblMsg.Text = "Sin Plata suficiente. ¡Se gana entrenando! 💪"
		return
	end
	plata = plata - costo
	nivelCasa = nivelCasa + 1
	construirCasa()
	lblMsg.TextColor3 = Color3.fromRGB(134, 239, 172)
	lblMsg.Text = "¡Tu Casa evolucionó a nivel " .. nivelCasa .. "! 🎉"
	actualizarUI()
end)

-- ---------- Arranque ----------
construirCasa()
actualizarUI()
