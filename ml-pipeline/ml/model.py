from __future__ import annotations

import torch
import torch.nn as nn


class LSTMAutoencoder(nn.Module):
    """Sequence-to-sequence LSTM autoencoder.

    - Encoder reads input sequence (B,T,F) and outputs final hidden state.
    - Decoder receives zeros and reconstructs the original sequence.
    """

    def __init__(self, input_dim: int, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.encoder = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        self.decoder = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        self.to_hidden = nn.Linear(hidden_dim, hidden_dim)
        self.out = nn.Linear(hidden_dim, input_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B,T,F)
        B, T, _ = x.shape

        _, (h, c) = self.encoder(x)           # h/c: (L,B,H)

        # Decoder inputs: repeat a learned projection of last layer hidden across time
        h_last = h[-1]                        # (B,H)
        dec_in_step = torch.tanh(self.to_hidden(h_last)).unsqueeze(1)  # (B,1,H)
        dec_in = dec_in_step.repeat(1, T, 1)  # (B,T,H)

        y, _ = self.decoder(dec_in, (h, c))   # y: (B,T,H)
        recon = self.out(y)                   # (B,T,F)
        return recon
