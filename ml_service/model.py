import torch
import torch.nn as nn


class LSTMAutoencoder(nn.Module):
    """
    Simple LSTM autoencoder for multivariate time series.
    Input:  (B, T, F)
    Output: (B, T, F) reconstruction
    """
    def __init__(self, input_dim: int, hidden_dim: int = 32, num_layers: int = 1, dropout: float = 0.1):
        super().__init__()
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
        _, (h, c) = self.encoder(x)           # (L,B,H)
        h_last = h[-1]                        # (B,H)
        B, T, _ = x.shape
        dec_in_step = torch.tanh(self.to_hidden(h_last)).unsqueeze(1)  # (B,1,H)
        dec_in = dec_in_step.repeat(1, T, 1)  # (B,T,H)
        y, _ = self.decoder(dec_in, (h, c))   # (B,T,H)
        return self.out(y)                    # (B,T,F)
