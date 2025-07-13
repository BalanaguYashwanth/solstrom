import React, { useState } from "react";
import { PopupProps } from "../../common/types";
import "./Popup.scss";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";

interface ExtendedPopupProps extends PopupProps {
  showSolanaPay?: boolean;
  handleAmount: (amount: string|number) => void;
}

const Popup: React.FC<ExtendedPopupProps> = ({
  open,
  heading = '',
  handleAmount,
  message,
  actions,
  showSolanaPay = false,
}) => {
  const { publicKey } = useWallet();
  const [amount, setAmount] = useState<number>(0.5);

  if (!open) return null;
  return (
    <div className="popup-overlay">
      <div className="popup-box">
        <h2 className="popup-heading">{heading}</h2>
        <div className="popup-message">
          {message}
          {showSolanaPay && (
            (publicKey ? <div style={{ marginTop: "1rem" }}>
              <input
                type="number"
                min="0.5"
                max="20"
                step="0.1"
                value={amount}
                onChange={(e) => {
                  setAmount(parseFloat(e.target.value))
                  handleAmount(parseFloat(e.target.value))
                }}
                placeholder="Enter SOL amount"
              />
              <p>Pay {amount} SOL</p>
            </div> : <div>
              <div className="wallet-button-container" style={{ margin: 16 }}>
                <WalletMultiButton className="wallet-button" />
              </div>
            </div>)
          )}
        </div>
        {actions && publicKey && <div className="popup-actions">{actions}</div>}
      </div>
    </div>
  );
};

export default Popup;