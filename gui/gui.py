import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class Dashboard(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Posh Copier")
        self.geometry("1400x850")

        self.build_ui()

    def stat_card(self, parent, title, value):

        frame = ctk.CTkFrame(parent, width=220, height=100)
        frame.pack_propagate(False)

        lbl1 = ctk.CTkLabel(
            frame,
            text=title,
            font=("Arial", 18, "bold")
        )

        lbl1.pack(pady=(15, 5))

        lbl2 = ctk.CTkLabel(
            frame,
            text=value,
            font=("Arial", 28)
        )

        lbl2.pack()

        return frame

    def build_ui(self):

        #################################################

        self.sidebar = ctk.CTkFrame(self, width=250)

        self.sidebar.pack(side="left", fill="y")

        title = ctk.CTkLabel(
            self.sidebar,
            text="POSH\nCOPIER",
            font=("Arial", 32, "bold")
        )

        title.pack(pady=30)

        ctk.CTkButton(
            self.sidebar,
            text="Dashboard"
        ).pack(pady=8)

        ctk.CTkButton(
            self.sidebar,
            text="Inventory"
        ).pack(pady=8)

        ctk.CTkButton(
            self.sidebar,
            text="Logs"
        ).pack(pady=8)

        ctk.CTkButton(
            self.sidebar,
            text="Settings"
        ).pack(pady=8)

        #################################################

        self.main = ctk.CTkFrame(self)

        self.main.pack(fill="both", expand=True, padx=20, pady=20)

        #################################################

        stats = ctk.CTkFrame(self.main)

        stats.pack(fill="x")

        self.card1 = self.stat_card(stats, "Listings Found", "0")
        self.card1.pack(side="left", padx=10)

        self.card2 = self.stat_card(stats, "Copied", "0")
        self.card2.pack(side="left", padx=10)

        self.card3 = self.stat_card(stats, "Remaining", "0")
        self.card3.pack(side="left", padx=10)

        self.card4 = self.stat_card(stats, "Errors", "0")
        self.card4.pack(side="left", padx=10)

        #################################################

        self.progress = ctk.CTkProgressBar(self.main)

        self.progress.pack(fill="x", pady=20)

        self.progress.set(0)

        #################################################

        self.current = ctk.CTkLabel(
            self.main,
            text="Current Listing: None",
            font=("Arial", 18)
        )

        self.current.pack()

        #################################################

        body = ctk.CTkFrame(self.main)

        body.pack(fill="both", expand=True, pady=20)

        #################################################

        preview = ctk.CTkFrame(body, width=300)

        preview.pack(side="left", fill="y", padx=10)

        preview.pack_propagate(False)

        ctk.CTkLabel(
            preview,
            text="Photo Preview",
            font=("Arial", 20, "bold")
        ).pack(pady=20)

        self.image = ctk.CTkLabel(
            preview,
            text="No Image"
        )

        self.image.pack(expand=True)

        #################################################

        logframe = ctk.CTkFrame(body)

        logframe.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            logframe,
            text="Activity Log",
            font=("Arial", 20, "bold")
        ).pack(pady=10)

        self.log = ctk.CTkTextbox(logframe)

        self.log.pack(fill="both", expand=True, padx=10, pady=10)

        #################################################

        buttons = ctk.CTkFrame(self.main)

        buttons.pack(fill="x")

        ctk.CTkButton(buttons, text="Start").pack(
            side="left",
            padx=10,
            pady=15
        )

        ctk.CTkButton(buttons, text="Pause").pack(
            side="left",
            padx=10
        )

        ctk.CTkButton(buttons, text="Resume").pack(
            side="left",
            padx=10
        )

        ctk.CTkButton(buttons, text="Stop").pack(
            side="left",
            padx=10
        )
        