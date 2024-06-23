'use client';

import { ChangeEvent, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import LoadingSpinner from '@/components/LoadingSpinner';

export default function Home() {
  const [url, setUrl] = useState('')
  const [isValidUrl, setIsValidUrl] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const router = useRouter()

  const handleUrlChange = (e: ChangeEvent<HTMLInputElement>) => {
    const inputUrl = e.target.value
    setUrl(inputUrl)
    
    const isValid = inputUrl.startsWith('https://docs.google.com/spreadsheets/')
    setIsValidUrl(isValid)
  }

  async function onSubmit() {
    if (isValidUrl) {
      setIsLoading(true);
      const res = await fetch('/api/getfreaky', {
        method: 'POST',
        body: JSON.stringify({
          user_url: url,
        })
      })
      const new_url = await res.json()
      setIsLoading(false);
      router.push(`/act?link=${encodeURIComponent(new_url.data)}`)
    }
  }

  return (
    <div className="p-10 space-y-4">
      <h1 className="pb-4 pl-2 font-bold text-2xl">freakinthesheets</h1>
      <Input
        type="text"
        value={url}
        onChange={handleUrlChange}
        placeholder="https://docs.google.com/spreadsheets/"
      />
      
      <Button
        onClick={onSubmit}
        disabled={isLoading}
      >
        {isLoading ? <LoadingSpinner /> : 'Get freaky!'}
      </Button>
    </div>
  )
}
